"""Outils partagés par les services métier."""
from __future__ import annotations

import math
from decimal import Decimal

from sqlalchemy.engine import Connection

from ..db import one, run

POINT = "ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography"


def setting(conn: Connection, key: str) -> tuple[Decimal, int]:
    """Valeur courante d'un paramètre et identifiant de sa version (pour la traçabilité)."""
    row = one(conn, "SELECT value, version_id FROM setting_versions WHERE key = :k AND is_current", k=key)
    return row["value"], row["version_id"]


def notify(conn: Connection, user_id, kind: str, message: str, ref_code: str | None = None) -> None:
    run(conn, "INSERT INTO notifications (user_id, kind, message, ref_code) VALUES (:u, :k, :m, :r)",
        u=user_id, k=kind, m=message, r=ref_code)


def fcfa(x) -> int:
    """Arrondi au franc le plus proche (les montants sont des entiers)."""
    return int(Decimal(x).quantize(Decimal("1"), rounding="ROUND_HALF_UP"))


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))
