"""Historisation SCD2 générique.

Un changement ferme la version courante et insère la nouvelle, dans la transaction de l'appelant.
Aucune ligne n'est jamais supprimée ni réécrite (la base le garantit aussi par déclencheurs).
"""
from __future__ import annotations

from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..errors import not_found

# table de versions -> colonne clé
TABLES = {
    "user_versions": "user_id",
    "waste_offer_versions": "offer_id",
    "setting_versions": "key",
    "ingredient_versions": "ingredient_id",
    "animal_profile_versions": "profile_id",
}
_TECH = {"version_id", "valid_from", "valid_to", "is_current"}


def current(conn: Connection, table: str, key, lock: bool = False) -> dict:
    col = TABLES[table]
    sql = f"SELECT * FROM {table} WHERE {col} = :k AND is_current" + (" FOR UPDATE" if lock else "")
    row = conn.execute(text(sql), {"k": key}).mappings().first()
    if not row:
        raise not_found(f"aucune version courante pour {key}")
    return dict(row)


def change(conn: Connection, table: str, key, changes: dict, geo: dict | None = None) -> dict:
    """Crée une nouvelle version avec `changes` appliqués. `geo` = {"location": (lat, lng)}."""
    col = TABLES[table]
    cur = current(conn, table, key, lock=True)
    values = {k: v for k, v in cur.items() if k not in _TECH and k != "location"}
    values.update({k: v for k, v in changes.items() if k != "location"})

    ts = conn.execute(text("SELECT clock_timestamp() AS ts")).scalar_one()
    conn.execute(
        text(f"UPDATE {table} SET valid_to = :ts, is_current = false WHERE version_id = :v"),
        {"ts": ts, "v": cur["version_id"]},
    )

    cols = list(values.keys())
    params = {k: Jsonb(v) if isinstance(v, (dict, list)) else v for k, v in values.items()}
    exprs = [f":{c}" for c in cols]
    if "location" in cur:
        cols.append("location")
        if geo and geo.get("location"):
            lat, lng = geo["location"]
            params["_lat"], params["_lng"] = lat, lng
            exprs.append("ST_SetSRID(ST_MakePoint(:_lng, :_lat), 4326)::geography")
        else:
            params["_prev"] = cur["version_id"]
            exprs.append(f"(SELECT location FROM {table} WHERE version_id = :_prev)")
    cols.append("valid_from")
    exprs.append(":_ts")
    params["_ts"] = ts
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(exprs)}) RETURNING *"
    # Les colonnes ENUM et JSONB sont passées en texte : PostgreSQL convertit.
    new = conn.execute(text(sql), params).mappings().first()
    return dict(new)


def history(conn: Connection, table: str, key) -> list[dict]:
    col = TABLES[table]
    sql = f"SELECT * FROM {table} WHERE {col} = :k ORDER BY valid_from"
    return [dict(r) for r in conn.execute(text(sql), {"k": key}).mappings().all()]
