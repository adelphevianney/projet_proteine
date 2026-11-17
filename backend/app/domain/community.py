"""Prix communautaires, litiges, notifications, élevages."""
from __future__ import annotations

from ..db import one, rows, run, transaction
from ..errors import DomainError, conflict, not_found
from .common import notify

PRICE_ITEMS = {
    "tourteau_soja": "Tourteau de soja", "mais": "Maïs grain", "son_ble": "Son de blé",
    "farine_poisson": "Farine de poisson", "farine_larves": "Farine de larves",
    "poulet_vif": "Poulet vif (kg)", "oeuf_plateau": "Plateau de 30 œufs",
}
MIN_REPORTERS = 3


def report_price(user: dict, item: str, price: int, commune: str | None) -> dict:
    if item not in PRICE_ITEMS:
        raise DomainError(422, "produit inconnu")
    with transaction(user["id"]) as conn:
        return one(conn, """INSERT INTO price_reports (user_id, item, price_fcfa_kg, commune)
                            VALUES (:u, :i, :p, :c) RETURNING id, item, price_fcfa_kg, created_at""",
                   u=user["id"], i=item, p=price, c=commune or user.get("commune"))


def community_prices() -> list[dict]:
    """Prix médian dès que 3 personnes ont déclaré (dernière déclaration de chacun sur 90 jours)."""
    with transaction() as conn:
        stats = rows(conn, """
            WITH last AS (
              SELECT DISTINCT ON (item, user_id) item, user_id, price_fcfa_kg, created_at
              FROM price_reports WHERE created_at > now() - interval '90 days'
              ORDER BY item, user_id, created_at DESC)
            SELECT item, count(*) AS reporters,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY price_fcfa_kg) AS median,
                   max(created_at) AS last_report
            FROM last GROUP BY item""")
    by_item = {s["item"]: s for s in stats}
    out = []
    for item, label in PRICE_ITEMS.items():
        s = by_item.get(item, {"reporters": 0, "median": None, "last_report": None})
        out.append({"item": item, "label": label, "reporters": s["reporters"],
                    "median": round(s["median"]) if s["reporters"] >= MIN_REPORTERS else None,
                    "last_report": s["last_report"], "needed": max(0, MIN_REPORTERS - s["reporters"])})
    return out


def open_dispute(user: dict, subject: str, body: str, ref_code: str | None) -> dict:
    with transaction(user["id"]) as conn:
        d = one(conn, """INSERT INTO disputes (author_id, subject, body, ref_code) VALUES (:u, :s, :b, :r)
                         RETURNING id, subject, status::text AS status, created_at""",
                u=user["id"], s=subject, b=body, r=ref_code)
        for admin in rows(conn, "SELECT id FROM users_current WHERE role = 'admin' AND status = 'active'"):
            notify(conn, admin["id"], "litige", f"Nouveau litige de {user['name']} : {subject}", ref_code)
        return d


DISPUTE_SQL = """SELECT d.id, d.subject, d.body, d.ref_code, d.status::text AS status, d.resolution,
                        d.created_at, d.resolved_at, a.name AS author_name, a.role::text AS author_role
                 FROM disputes d JOIN users_current a ON a.id = d.author_id"""


def my_disputes(user: dict) -> list[dict]:
    with transaction() as conn:
        return rows(conn, DISPUTE_SQL + " WHERE d.author_id = :u ORDER BY d.created_at DESC", u=user["id"])


def all_disputes(status: str | None) -> list[dict]:
    with transaction() as conn:
        return rows(conn, DISPUTE_SQL + " WHERE (CAST(:s AS text) IS NULL OR d.status::text = :s) "
                                        "ORDER BY d.created_at DESC", s=status)


def resolve_dispute(admin: dict, dispute_id, resolution: str) -> dict:
    with transaction(admin["id"]) as conn:
        d = one(conn, "SELECT id, author_id, status::text AS status, subject FROM disputes WHERE id = :id FOR UPDATE",
                id=dispute_id)
        if not d:
            raise not_found("litige introuvable")
        if d["status"] != "open":
            raise conflict("litige déjà résolu")
        run(conn, """UPDATE disputes SET status = 'resolved', resolution = :r, resolved_by = :a, resolved_at = now()
                     WHERE id = :id""", r=resolution, a=admin["id"], id=dispute_id)
        notify(conn, d["author_id"], "litige", f"Votre litige « {d['subject']} » a reçu une réponse : {resolution}")
        return one(conn, DISPUTE_SQL + " WHERE d.id = :id", id=dispute_id)


def notifications(user: dict) -> list[dict]:
    with transaction() as conn:
        return rows(conn, """SELECT id, kind, message, ref_code, read_at, created_at FROM notifications
                             WHERE user_id = :u ORDER BY created_at DESC LIMIT 100""", u=user["id"])


def mark_read(user: dict) -> dict:
    with transaction(user["id"]) as conn:
        run(conn, "UPDATE notifications SET read_at = now() WHERE user_id = :u AND read_at IS NULL", u=user["id"])
    return {"ok": True}


def add_herd(user: dict, profile_id: str, name: str, headcount: int) -> dict:
    with transaction(user["id"]) as conn:
        return one(conn, """INSERT INTO herds (breeder_id, profile_id, name, headcount) VALUES (:u, :p, :n, :h)
                            RETURNING id, profile_id, name, headcount, created_at""",
                   u=user["id"], p=profile_id, n=name, h=headcount)


def herds(user: dict) -> list[dict]:
    with transaction() as conn:
        return rows(conn, """SELECT h.id, h.profile_id, p.name AS profile_name, p.family, h.name, h.headcount, h.created_at
                             FROM herds h JOIN animal_profiles p ON p.id = h.profile_id
                             WHERE h.breeder_id = :u ORDER BY h.created_at DESC""", u=user["id"])
