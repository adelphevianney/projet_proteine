"""Offres de déchets : publication, recherche par distance, réservation (transaction)."""
from __future__ import annotations

import re
import unicodedata

from ..db import one, rows, transaction
from ..errors import DomainError, conflict, forbidden, not_found
from ..repositories import scd2
from .common import POINT, notify, setting

OFFER_SQL = """
SELECT o.id, o.producer_id, o.waste_type_id, t.name AS waste_type, o.created_at, v.version_id,
       v.quantity_kg, v.price_per_kg, v.frequency, v.description, v.commune, v.status::text AS status,
       ST_Y(v.location::geometry) AS lat, ST_X(v.location::geometry) AS lng, v.valid_from AS updated_at,
       l.code AS lot_code, l.status::text AS lot_status
FROM waste_offers o
JOIN waste_offer_versions v ON v.offer_id = o.id AND v.is_current
JOIN waste_types t ON t.id = o.waste_type_id
LEFT JOIN waste_lots l ON l.offer_id = o.id
"""

_TYPES = [
    ("manioc", ("manioc", "attieke", "epluchure", "cossette")),
    ("cajou", ("cajou", "anacarde")),
    ("cacao", ("cacao", "cabosse")),
    ("marche", ("marche", "legume", "fruit", "banane", "tomate")),
]
_UNITS = {"kg": 1, "kilo": 1, "kilos": 1, "t": 1000, "tonne": 1000, "tonnes": 1000, "sac": 50, "sacs": 50}


def _plain(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def parse_text(text: str) -> dict:
    """Comprend « 300 kg de manioc par semaine » ou « 2 tonnes de cabosses chaque mois »."""
    t = _plain(text)
    out: dict = {"quantity_kg": None, "waste_type_id": None, "frequency": "ponctuelle"}
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(kg|kilos?|tonnes?|t|sacs?)\b", t)
    if m:
        out["quantity_kg"] = round(float(m.group(1).replace(",", ".")) * _UNITS[m.group(2)], 1)
    for type_id, words in _TYPES:
        if any(w in t for w in words):
            out["waste_type_id"] = type_id
            break
    if re.search(r"par jour|chaque jour|quotidien|tous les jours", t):
        out["frequency"] = "quotidienne"
    elif re.search(r"par semaine|chaque semaine|hebdo", t):
        out["frequency"] = "hebdomadaire"
    elif re.search(r"par mois|chaque mois|mensuel", t):
        out["frequency"] = "mensuelle"
    return out


def create(user: dict, data: dict) -> dict:
    lat = data["lat"] if data.get("lat") is not None else user.get("lat")
    lng = data["lng"] if data.get("lng") is not None else user.get("lng")
    if lat is None or lng is None:
        raise DomainError(422, "indiquez le lieu du gisement sur la carte")
    with transaction(user["id"]) as conn:
        price = data.get("price_per_kg")
        if price is None:
            price = int(setting(conn, "waste_price_per_kg")[0])
        offer_id = one(conn, """INSERT INTO waste_offers (producer_id, waste_type_id) VALUES (:p, :t)
                                RETURNING id""", p=user["id"], t=data["waste_type_id"])["id"]
        one(conn, f"""INSERT INTO waste_offer_versions
                        (offer_id, quantity_kg, price_per_kg, frequency, description, commune, location, status)
                      VALUES (:o, :q, :pr, :f, :d, :c, {POINT}, 'published') RETURNING version_id""",
            o=offer_id, q=data["quantity_kg"], pr=price, f=data.get("frequency") or "ponctuelle",
            d=data.get("description"), c=data.get("commune") or user.get("commune"), lat=lat, lng=lng)
        return one(conn, OFFER_SQL + " WHERE o.id = :id", id=offer_id)


def _own_offer(conn, user, offer_id) -> dict:
    owner = one(conn, "SELECT producer_id FROM waste_offers WHERE id = :id FOR UPDATE", id=offer_id)
    if not owner:
        raise not_found("offre introuvable")
    if owner["producer_id"] != user["id"]:
        raise forbidden("cette offre ne vous appartient pas")
    return scd2.current(conn, "waste_offer_versions", offer_id)


def update(user: dict, offer_id, data: dict) -> dict:
    """Modifier quantité, prix ou lieu d'une offre encore publiée : nouvelle version SCD2."""
    with transaction(user["id"]) as conn:
        cur = _own_offer(conn, user, offer_id)
        if cur["status"] != "published":
            raise conflict("seule une offre publiée et non réservée peut être modifiée")
        geo = {"location": (data["lat"], data["lng"])} if data.get("lat") is not None else None
        changes = {k: data[k] for k in ("quantity_kg", "price_per_kg", "frequency", "description", "commune")
                   if data.get(k) is not None}
        scd2.change(conn, "waste_offer_versions", offer_id, changes, geo)
        return one(conn, OFFER_SQL + " WHERE o.id = :id", id=offer_id)


def cancel(user: dict, offer_id) -> dict:
    with transaction(user["id"]) as conn:
        cur = _own_offer(conn, user, offer_id)
        if cur["status"] != "published":
            raise conflict("une offre réservée ne peut plus être annulée")
        scd2.change(conn, "waste_offer_versions", offer_id, {"status": "cancelled"})
        return one(conn, OFFER_SQL + " WHERE o.id = :id", id=offer_id)


def mine(user: dict) -> list[dict]:
    with transaction() as conn:
        return rows(conn, OFFER_SQL + " WHERE o.producer_id = :u ORDER BY o.created_at DESC", u=user["id"])


def history(offer_id) -> list[dict]:
    with transaction() as conn:
        return rows(conn, """SELECT version_id, quantity_kg, price_per_kg, frequency, status::text AS status,
                                    ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng,
                                    valid_from, valid_to, is_current
                             FROM waste_offer_versions WHERE offer_id = :o ORDER BY valid_from""", o=offer_id)


def nearby(user: dict, lat: float | None, lng: float | None, km: float) -> list[dict]:
    lat, lng = lat if lat is not None else user.get("lat"), lng if lng is not None else user.get("lng")
    if lat is None or lng is None:
        raise DomainError(422, "position inconnue : renseignez la position de la ferme")
    with transaction() as conn:
        return rows(conn, f"""
            SELECT o.id, o.waste_type_id, t.name AS waste_type, t.risk, v.quantity_kg, v.price_per_kg,
                   v.frequency, v.description, v.commune,
                   ST_Y(v.location::geometry) AS lat, ST_X(v.location::geometry) AS lng,
                   round((ST_Distance(v.location, {POINT}) / 1000)::numeric, 1) AS distance_km,
                   p.name AS producer_name
            FROM waste_offers o
            JOIN waste_offer_versions v ON v.offer_id = o.id AND v.is_current AND v.status = 'published'
            JOIN waste_types t ON t.id = o.waste_type_id
            JOIN users_current p ON p.id = o.producer_id
            WHERE ST_DWithin(v.location, {POINT}, :m)
            ORDER BY v.location <-> {POINT}""", lat=lat, lng=lng, m=km * 1000)


def reserve(user: dict, offer_id) -> dict:
    """Réservation par une ferme : offre réservée + lot créé + collecteur affecté, en une transaction."""
    with transaction(user["id"]) as conn:
        # Verrou sur l'identité de l'offre : deux fermes ne peuvent pas passer en même temps.
        if not one(conn, "SELECT id FROM waste_offers WHERE id = :id FOR UPDATE", id=offer_id):
            raise not_found("offre introuvable")
        cur = scd2.current(conn, "waste_offer_versions", offer_id)
        if cur["status"] != "published":
            raise conflict("cette offre n'est plus disponible")
        new = scd2.change(conn, "waste_offer_versions", offer_id, {"status": "reserved"})
        collector = one(conn, """SELECT c.id FROM users_current c
                                 WHERE c.role = 'collector' AND c.status = 'active' AND c.location IS NOT NULL
                                 ORDER BY c.location <-> (SELECT location FROM waste_offer_versions
                                                          WHERE version_id = :v)
                                 LIMIT 1""", v=new["version_id"])
        lot = one(conn, """INSERT INTO waste_lots (offer_id, offer_version_id, farm_id, collector_id)
                           VALUES (:o, :v, :f, :c) RETURNING id, code""",
                  o=offer_id, v=new["version_id"], f=user["id"], c=collector["id"] if collector else None)
        producer = one(conn, "SELECT producer_id FROM waste_offers WHERE id = :id", id=offer_id)["producer_id"]
        notify(conn, producer, "reservation",
               f"Votre offre de {cur['quantity_kg']} kg a été réservée par {user['name']}.", lot["code"])
        if collector:
            notify(conn, collector["id"], "tournee", "Un nouvel enlèvement a été ajouté à votre tournée.", lot["code"])
        return {"lot_id": lot["id"], "lot_code": lot["code"],
                "collector_id": collector["id"] if collector else None}
