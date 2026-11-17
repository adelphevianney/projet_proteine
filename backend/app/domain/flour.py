"""Farine : déclaration d'un lot relié à ses déchets d'origine, stock, offre aux éleveurs."""
from __future__ import annotations

from ..db import one, rows, run, transaction
from ..errors import DomainError, conflict
from .common import POINT

BATCH_SQL = """
SELECT b.id, b.code, b.quantity_kg, b.stock_kg, b.price_per_kg, b.status::text AS status, b.created_at,
       b.farm_id, f.name AS farm_name, f.commune,
       (SELECT array_agg(w.code ORDER BY w.code) FROM flour_batch_sources s
          JOIN waste_lots w ON w.id = s.waste_lot_id WHERE s.flour_batch_id = b.id) AS source_codes
FROM flour_batches b JOIN users_current f ON f.id = b.farm_id
"""


def declare(user: dict, source_lot_ids: list, quantity_kg, price_per_kg: int) -> dict:
    if not source_lot_ids:
        raise DomainError(422, "une farine doit être reliée à au moins un lot de déchets")
    with transaction(user["id"]) as conn:
        lots = rows(conn, """SELECT id, code, farm_id, status::text AS status FROM waste_lots
                             WHERE id = ANY(:ids) ORDER BY id FOR UPDATE""", ids=list(source_lot_ids))
        if len(lots) != len(set(source_lot_ids)):
            raise DomainError(422, "lot de déchets inconnu")
        for lot in lots:
            if lot["farm_id"] != user["id"]:
                raise conflict(f"le lot {lot['code']} n'appartient pas à votre ferme")
            if lot["status"] != "received":
                raise conflict(f"le lot {lot['code']} n'est pas réceptionné et disponible ({lot['status']})")
        batch = one(conn, """INSERT INTO flour_batches (farm_id, quantity_kg, stock_kg, price_per_kg)
                             VALUES (:f, :q, :q, :p) RETURNING id""", f=user["id"], q=quantity_kg, p=price_per_kg)
        for lot in lots:
            run(conn, "INSERT INTO flour_batch_sources (flour_batch_id, waste_lot_id) VALUES (:b, :l)",
                b=batch["id"], l=lot["id"])
            run(conn, "UPDATE waste_lots SET status = 'used', version = version + 1, updated_at = now() "
                      "WHERE id = :id", id=lot["id"])
        return one(conn, BATCH_SQL + " WHERE b.id = :id", id=batch["id"])


def mine(user: dict) -> list[dict]:
    with transaction() as conn:
        return rows(conn, BATCH_SQL + " WHERE b.farm_id = :u ORDER BY b.created_at DESC", u=user["id"])


def available(user: dict, lat: float | None, lng: float | None) -> list[dict]:
    """Farine disponible, triée par prix puis par distance."""
    lat, lng = lat if lat is not None else user.get("lat"), lng if lng is not None else user.get("lng")
    with transaction() as conn:
        dist = (f"round((ST_Distance(f.location, {POINT}) / 1000)::numeric, 1)"
                if lat is not None and lng is not None else "NULL::numeric")
        return rows(conn, f"""
            SELECT b.id, b.code, b.stock_kg, b.price_per_kg, b.created_at, f.name AS farm_name, f.commune,
                   {dist} AS distance_km
            FROM flour_batches b JOIN users_current f ON f.id = b.farm_id
            WHERE b.status = 'available' AND b.stock_kg > 0
            ORDER BY b.price_per_kg, distance_km NULLS LAST""", lat=lat, lng=lng)
