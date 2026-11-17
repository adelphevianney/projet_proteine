"""Paiements : enregistrés dans l'application, réglés hors plateforme, confirmés par référence."""
from __future__ import annotations

from ..db import one, rows, run, transaction
from ..errors import DomainError, conflict, forbidden, not_found
from .common import notify

PAY_SQL = """
SELECT p.id, p.kind::text AS kind, p.amount_fcfa, p.status::text AS status, p.reference, p.created_at,
       p.settled_at, p.payer_id, p.payee_id, payer.name AS payer_name,
       coalesce(payee.name, 'Plateforme') AS payee_name,
       coalesce(l.code, b.code) AS ref_code
FROM payments p
JOIN users_current payer ON payer.id = p.payer_id
LEFT JOIN users_current payee ON payee.id = p.payee_id
LEFT JOIN waste_lots l ON l.id = p.waste_lot_id
LEFT JOIN orders o ON o.id = p.order_id
LEFT JOIN flour_batches b ON b.id = o.flour_batch_id
"""


def mine(user: dict) -> dict:
    with transaction() as conn:
        items = rows(conn, PAY_SQL + " WHERE p.payer_id = :u OR p.payee_id = :u ORDER BY p.created_at DESC",
                     u=user["id"])
    to_pay = sum(p["amount_fcfa"] for p in items if p["payer_id"] == user["id"] and p["status"] == "due")
    to_receive = sum(p["amount_fcfa"] for p in items if p["payee_id"] == user["id"] and p["status"] == "due")
    received = sum(p["amount_fcfa"] for p in items if p["payee_id"] == user["id"] and p["status"] == "settled")
    return {"items": items, "to_pay": to_pay, "to_receive": to_receive, "received": received}


def all_payments(status: str | None) -> list[dict]:
    with transaction() as conn:
        return rows(conn, PAY_SQL + " WHERE (CAST(:s AS text) IS NULL OR p.status::text = :s) "
                                    "ORDER BY p.created_at DESC LIMIT 500", s=status)


def confirm(user: dict, payment_id, reference: str) -> dict:
    reference = (reference or "").strip()
    if len(reference) < 4:
        raise DomainError(422, "saisissez la référence du paiement (mobile money ou reçu)")
    with transaction(user["id"]) as conn:
        p = one(conn, "SELECT * FROM payments WHERE id = :id FOR UPDATE", id=payment_id)
        if not p:
            raise not_found("paiement introuvable")
        if p["payer_id"] != user["id"]:
            raise forbidden("seule la personne qui paie confirme le paiement")
        if p["status"] == "settled" and p["reference"] == reference:
            return one(conn, PAY_SQL + " WHERE p.id = :id", id=payment_id)  # double envoi : sans effet
        if p["status"] != "due":
            raise conflict(f"paiement déjà {p['status']}")
        run(conn, "UPDATE payments SET status = 'settled', reference = :r, settled_at = now() WHERE id = :id",
            r=reference, id=payment_id)
        if p["payee_id"]:
            notify(conn, p["payee_id"], "paiement",
                   f"Paiement de {p['amount_fcfa']} FCFA confirmé par {user['name']} (réf. {reference}).")
        return one(conn, PAY_SQL + " WHERE p.id = :id", id=payment_id)
