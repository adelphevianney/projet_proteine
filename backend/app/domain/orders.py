"""Commandes de farine : décrément de stock conditionnel, idempotence, livraison, annulation."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from ..db import one, rows, run, transaction
from ..errors import conflict, forbidden, not_found
from .common import fcfa, notify, setting

ORDER_SQL = """
SELECT o.id, o.quantity_kg, o.unit_price, o.total_fcfa, o.status::text AS status, o.created_at, o.updated_at,
       o.breeder_id, b.id AS flour_batch_id, b.code AS flour_code, b.farm_id, f.name AS farm_name,
       e.name AS breeder_name, e.phone AS breeder_phone, e.commune AS breeder_commune
FROM orders o
JOIN flour_batches b ON b.id = o.flour_batch_id
JOIN users_current f ON f.id = b.farm_id
JOIN users_current e ON e.id = o.breeder_id
"""


def create(user: dict, batch_id, quantity_kg: Decimal, idempotency_key: str | None) -> dict:
    if idempotency_key:
        with transaction() as conn:
            existing = one(conn, ORDER_SQL + " WHERE o.idempotency_key = :k AND o.breeder_id = :u",
                           k=idempotency_key, u=user["id"])
        if existing:
            return existing
    try:
        with transaction(user["id"]) as conn:
            # Décrément conditionnel : jamais de stock négatif, même avec des commandes simultanées.
            batch = one(conn, """UPDATE flour_batches
                                 SET stock_kg = stock_kg - :q, version = version + 1, updated_at = now(),
                                     status = CASE WHEN stock_kg - :q = 0 THEN 'sold_out'::flour_status
                                                   ELSE status END
                                 WHERE id = :id AND status = 'available' AND stock_kg >= :q
                                 RETURNING id, code, farm_id, price_per_kg, stock_kg""", q=quantity_kg, id=batch_id)
            if not batch:
                raise conflict("stock insuffisant ou farine indisponible")
            total = fcfa(Decimal(quantity_kg) * batch["price_per_kg"])
            order = one(conn, """INSERT INTO orders (breeder_id, flour_batch_id, quantity_kg, unit_price, total_fcfa,
                                                     idempotency_key)
                                 VALUES (:u, :b, :q, :p, :t, :k) RETURNING id""",
                        u=user["id"], b=batch_id, q=quantity_kg, p=batch["price_per_kg"], t=total, k=idempotency_key)
            run(conn, """INSERT INTO payments (kind, payer_id, payee_id, order_id, amount_fcfa)
                         VALUES ('flour', :payer, :payee, :o, :amt)""",
                payer=user["id"], payee=batch["farm_id"], o=order["id"], amt=total)
            rate, rate_v = setting(conn, "commission_rate")
            run(conn, """INSERT INTO payments (kind, payer_id, payee_id, order_id, amount_fcfa, tariff_version_id)
                         VALUES ('commission', :payer, NULL, :o, :amt, :tv)""",
                payer=batch["farm_id"], o=order["id"], amt=fcfa(total * rate), tv=rate_v)
            notify(conn, batch["farm_id"], "commande",
                   f"Nouvelle commande : {quantity_kg} kg de farine {batch['code']} par {user['name']}.", batch["code"])
            return one(conn, ORDER_SQL + " WHERE o.id = :id", id=order["id"])
    except IntegrityError as exc:
        # Deux envois simultanés avec la même clé : on renvoie la commande déjà créée.
        if idempotency_key and "idempotency_key" in str(exc.orig):
            with transaction() as conn:
                existing = one(conn, ORDER_SQL + " WHERE o.idempotency_key = :k AND o.breeder_id = :u",
                               k=idempotency_key, u=user["id"])
            if existing:
                return existing
            raise conflict("clé d'idempotence déjà utilisée") from exc
        raise


def mine(user: dict) -> list[dict]:
    with transaction() as conn:
        return rows(conn, ORDER_SQL + " WHERE o.breeder_id = :u ORDER BY o.created_at DESC", u=user["id"])


def incoming(user: dict) -> list[dict]:
    with transaction() as conn:
        return rows(conn, ORDER_SQL + " WHERE b.farm_id = :u ORDER BY o.created_at DESC", u=user["id"])


def _lock(conn, order_id) -> dict:
    o = one(conn, """SELECT o.*, b.farm_id, b.code FROM orders o JOIN flour_batches b ON b.id = o.flour_batch_id
                     WHERE o.id = :id FOR UPDATE OF o""", id=order_id)
    if not o:
        raise not_found("commande introuvable")
    return o


def deliver(user: dict, order_id) -> dict:
    with transaction(user["id"]) as conn:
        o = _lock(conn, order_id)
        if o["farm_id"] != user["id"]:
            raise forbidden("cette commande n'est pas pour votre ferme")
        if o["status"] != "ordered":
            raise conflict(f"commande déjà {o['status']}")
        run(conn, "UPDATE orders SET status = 'delivered', version = version + 1, updated_at = now() WHERE id = :id",
            id=order_id)
        notify(conn, o["breeder_id"], "livraison", f"Votre farine {o['code']} a été livrée.", o["code"])
        return one(conn, ORDER_SQL + " WHERE o.id = :id", id=order_id)


def cancel(user: dict, order_id) -> dict:
    with transaction(user["id"]) as conn:
        o = _lock(conn, order_id)
        if o["breeder_id"] != user["id"]:
            raise forbidden("cette commande n'est pas la vôtre")
        if o["status"] != "ordered":
            raise conflict(f"commande déjà {o['status']}")
        run(conn, "UPDATE orders SET status = 'cancelled', version = version + 1, updated_at = now() WHERE id = :id",
            id=order_id)
        run(conn, """UPDATE flour_batches SET stock_kg = stock_kg + :q, version = version + 1, updated_at = now(),
                     status = CASE WHEN status = 'sold_out' THEN 'available'::flour_status ELSE status END
                     WHERE id = :b""", q=o["quantity_kg"], b=o["flour_batch_id"])
        run(conn, "UPDATE payments SET status = 'cancelled' WHERE order_id = :id AND status = 'due'", id=order_id)
        notify(conn, o["farm_id"], "commande", f"Commande annulée sur la farine {o['code']}.", o["code"])
        return one(conn, ORDER_SQL + " WHERE o.id = :id", id=order_id)
