"""Lots de déchets : collecte, réception avec qualité, tournée, retrait en cascade."""
from __future__ import annotations

from decimal import Decimal

from ..db import one, rows, run, run_serializable, transaction
from ..errors import DomainError, conflict, forbidden, not_found
from .common import fcfa, haversine_km, notify, setting

LOT_SQL = """
SELECT l.id, l.code, l.status::text AS status, l.quality::text AS quality, l.weight_kg, l.created_at,
       l.updated_at, l.offer_id, l.farm_id, l.collector_id, o.producer_id,
       t.id AS waste_type_id, t.name AS waste_type, v.quantity_kg AS announced_kg, v.price_per_kg,
       v.commune, ST_Y(v.location::geometry) AS lat, ST_X(v.location::geometry) AS lng,
       p.name AS producer_name, f.name AS farm_name, c.name AS collector_name
FROM waste_lots l
JOIN waste_offers o ON o.id = l.offer_id
JOIN waste_offer_versions v ON v.version_id = l.offer_version_id
JOIN waste_types t ON t.id = o.waste_type_id
JOIN users_current p ON p.id = o.producer_id
JOIN users_current f ON f.id = l.farm_id
LEFT JOIN users_current c ON c.id = l.collector_id
"""


def _lock(conn, lot_id) -> dict:
    lot = one(conn, """SELECT l.*, o.producer_id, v.price_per_kg
                       FROM waste_lots l
                       JOIN waste_offers o ON o.id = l.offer_id
                       JOIN waste_offer_versions v ON v.version_id = l.offer_version_id
                       WHERE l.id = :id FOR UPDATE OF l""", id=lot_id)
    if not lot:
        raise not_found("lot introuvable")
    return lot


def for_user(user: dict) -> list[dict]:
    col = {"farm": "l.farm_id", "producer": "o.producer_id", "collector": "l.collector_id"}.get(user["role"])
    with transaction() as conn:
        if user["role"] == "admin":
            return rows(conn, LOT_SQL + " ORDER BY l.created_at DESC LIMIT 200")
        if not col:
            return []
        return rows(conn, LOT_SQL + f" WHERE {col} = :u ORDER BY l.created_at DESC", u=user["id"])


def tour(user: dict) -> dict:
    """Tournée du collecteur : du plus proche au plus lointain (plus proche voisin), distance totale."""
    with transaction() as conn:
        stops = rows(conn, LOT_SQL + " WHERE l.collector_id = :u AND l.status = 'reserved'", u=user["id"])
    pos = (user["lat"], user["lng"]) if user.get("lat") is not None else None
    ordered, total = [], 0.0
    remaining = list(stops)
    while remaining:
        if pos is None:
            nxt = remaining[0]
            dist = 0.0
        else:
            nxt = min(remaining, key=lambda s: haversine_km(pos, (s["lat"], s["lng"])))
            dist = haversine_km(pos, (nxt["lat"], nxt["lng"]))
        total += dist
        nxt["leg_km"] = round(dist, 1)
        ordered.append(nxt)
        remaining.remove(nxt)
        pos = (nxt["lat"], nxt["lng"])
    return {"stops": ordered, "total_km": round(total, 1)}


def collect(user: dict, lot_id, weight_kg: Decimal) -> dict:
    """Le collecteur confirme l'enlèvement avec le poids pesé ; sa rémunération devient due."""
    with transaction(user["id"]) as conn:
        lot = _lock(conn, lot_id)
        if lot["collector_id"] != user["id"]:
            raise forbidden("ce lot n'est pas dans votre tournée")
        if lot["status"] != "reserved":
            raise conflict(f"lot déjà {lot['status']}")
        run(conn, """UPDATE waste_lots SET status = 'collected', weight_kg = :w, version = version + 1,
                     updated_at = now() WHERE id = :id""", w=weight_kg, id=lot_id)
        rate, rate_v = setting(conn, "collection_price_per_kg")
        run(conn, """INSERT INTO payments (kind, payer_id, payee_id, waste_lot_id, amount_fcfa, tariff_version_id)
                     VALUES ('collection', :payer, :payee, :lot, :amt, :tv)""",
            payer=lot["farm_id"], payee=user["id"], lot=lot_id, amt=fcfa(Decimal(weight_kg) * rate), tv=rate_v)
        notify(conn, lot["farm_id"], "collecte", f"Lot {lot['code']} collecté : {weight_kg} kg.", lot["code"])
        notify(conn, lot["producer_id"], "collecte", f"Vos déchets ont été enlevés ({weight_kg} kg).", lot["code"])
        return one(conn, LOT_SQL + " WHERE l.id = :id", id=lot_id)


def receive(user: dict, lot_id, quality: str) -> dict:
    """La ferme contrôle la qualité. Conforme ou dégradé : paiement dû au producteur + commission."""
    if quality not in ("conforme", "degrade", "rejete"):
        raise DomainError(422, "qualité : conforme, degrade ou rejete")
    with transaction(user["id"]) as conn:
        lot = _lock(conn, lot_id)
        if lot["farm_id"] != user["id"]:
            raise forbidden("ce lot n'est pas à votre ferme")
        if lot["status"] != "collected":
            raise conflict(f"réception impossible : lot {lot['status']}")
        status = "rejected" if quality == "rejete" else "received"
        run(conn, """UPDATE waste_lots SET status = :s, quality = :q, version = version + 1, updated_at = now()
                     WHERE id = :id""", s=status, q=quality, id=lot_id)
        if status == "received":
            amount = Decimal(lot["weight_kg"]) * lot["price_per_kg"]
            tariff_v = None
            if quality == "degrade":
                discount, tariff_v = setting(conn, "degraded_discount")
                amount *= 1 - discount
            amount = fcfa(amount)
            run(conn, """INSERT INTO payments (kind, payer_id, payee_id, waste_lot_id, amount_fcfa, tariff_version_id)
                         VALUES ('waste', :payer, :payee, :lot, :amt, :tv)""",
                payer=user["id"], payee=lot["producer_id"], lot=lot_id, amt=amount, tv=tariff_v)
            rate, rate_v = setting(conn, "commission_rate")
            run(conn, """INSERT INTO payments (kind, payer_id, payee_id, waste_lot_id, amount_fcfa, tariff_version_id)
                         VALUES ('commission', :payer, NULL, :lot, :amt, :tv)""",
                payer=lot["producer_id"], lot=lot_id, amt=fcfa(amount * rate), tv=rate_v)
            label = "conforme" if quality == "conforme" else "dégradé (prix réduit de 30 %)"
            notify(conn, lot["producer_id"], "reception",
                   f"Lot {lot['code']} réceptionné, {label}. {amount} FCFA vous sont dus.", lot["code"])
        else:
            notify(conn, lot["producer_id"], "reception", f"Lot {lot['code']} rejeté au contrôle qualité.",
                   lot["code"])
        return one(conn, LOT_SQL + " WHERE l.id = :id", id=lot_id)


def _recall_flour(conn, batch_ids: list, reason: str, origin_code: str) -> dict:
    """Retire des lots de farine, annule les commandes non livrées et alerte les éleveurs."""
    stats = {"flour_batches": 0, "orders_cancelled": 0, "breeders_alerted": 0}
    if not batch_ids:
        return stats
    batches = rows(conn, """SELECT id, code, status::text AS status FROM flour_batches
                            WHERE id = ANY(:ids) ORDER BY id FOR UPDATE""", ids=batch_ids)
    for b in batches:
        if b["status"] != "recalled":
            run(conn, "UPDATE flour_batches SET status = 'recalled', version = version + 1, updated_at = now() "
                      "WHERE id = :id", id=b["id"])
            stats["flour_batches"] += 1
    orders = rows(conn, """SELECT o.id, o.breeder_id, o.status::text AS status, f.code
                           FROM orders o JOIN flour_batches f ON f.id = o.flour_batch_id
                           WHERE o.flour_batch_id = ANY(:ids) ORDER BY o.id FOR UPDATE OF o""", ids=batch_ids)
    alerted = set()
    for o in orders:
        if o["status"] == "ordered":
            run(conn, "UPDATE orders SET status = 'recalled', version = version + 1, updated_at = now() "
                      "WHERE id = :id", id=o["id"])
            run(conn, "UPDATE payments SET status = 'cancelled' WHERE order_id = :id AND status = 'due'", id=o["id"])
            stats["orders_cancelled"] += 1
        if o["status"] in ("ordered", "delivered") and o["breeder_id"] not in alerted:
            alerted.add(o["breeder_id"])
            notify(conn, o["breeder_id"], "retrait",
                   f"ALERTE : la farine {o['code']} est retirée ({reason}). Ne l'utilisez plus.", o["code"])
    stats["breeders_alerted"] = len(alerted)
    return stats


def recall(user: dict, lot_id, reason: str) -> dict:
    """Retrait d'un lot de déchets : farine dérivée et commandes concernées retirées, en SERIALIZABLE."""

    def work(conn):
        lot = _lock(conn, lot_id)
        if user["role"] != "admin" and lot["farm_id"] != user["id"]:
            raise forbidden("seule la ferme du lot ou l'administration peut le retirer")
        if lot["status"] in ("recalled", "rejected"):
            raise conflict(f"lot déjà {lot['status']}")
        run(conn, "UPDATE waste_lots SET status = 'recalled', version = version + 1, updated_at = now() "
                  "WHERE id = :id", id=lot_id)
        run(conn, """INSERT INTO recalls (waste_lot_id, reason, initiated_by) VALUES (:l, :r, :u)""",
            l=lot_id, r=reason, u=user["id"])
        batch_ids = [r["flour_batch_id"] for r in rows(
            conn, "SELECT flour_batch_id FROM flour_batch_sources WHERE waste_lot_id = :l", l=lot_id)]
        stats = _recall_flour(conn, batch_ids, reason, lot["code"])
        notify(conn, lot["producer_id"], "retrait", f"Le lot {lot['code']} a été retiré : {reason}.", lot["code"])
        return {"lot_code": lot["code"], **stats}

    return run_serializable(work, user["id"])


def recall_flour(user: dict, batch_id, reason: str) -> dict:
    def work(conn):
        b = one(conn, "SELECT id, code, farm_id, status::text AS status FROM flour_batches WHERE id = :id FOR UPDATE",
                id=batch_id)
        if not b:
            raise not_found("lot de farine introuvable")
        if user["role"] != "admin" and b["farm_id"] != user["id"]:
            raise forbidden("seule la ferme ou l'administration peut retirer ce lot")
        if b["status"] == "recalled":
            raise conflict("lot de farine déjà retiré")
        run(conn, "INSERT INTO recalls (flour_batch_id, reason, initiated_by) VALUES (:b, :r, :u)",
            b=batch_id, r=reason, u=user["id"])
        return {"flour_code": b["code"], **_recall_flour(conn, [batch_id], reason, b["code"])}

    return run_serializable(work, user["id"])
