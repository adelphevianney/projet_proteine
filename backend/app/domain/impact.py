"""Indicateurs d'impact, tenus à jour en lisant seulement les nouveaux changements (CDC)."""
from __future__ import annotations

from decimal import Decimal

from ..db import one, rows, run, transaction
from .common import setting

CONSUMER = "impact"


def _metrics_for(conn, change: dict) -> list[tuple[str, object]]:
    """Ce qu'un changement de statut ajoute aux totaux (liste vide s'il ne compte pas)."""
    old, new = change["old_data"] or {}, change["new_data"] or {}
    status = new.get("status")
    if old.get("status") == status:
        return []
    table = change["table_name"]
    if table == "waste_lots" and status == "received":
        return [("waste_received_kg", new["weight_kg"])]
    if table == "orders" and status == "delivered":
        return [("flour_delivered_kg", new["quantity_kg"])]
    if table != "payments" or status != "settled" or new["kind"] == "commission":
        return []
    out = [(f"revenue_{new['kind']}_fcfa", new["amount_fcfa"])]
    if new["kind"] in ("waste", "collection") and new.get("payee_id"):
        payee = one(conn, "SELECT is_woman FROM users_current WHERE id = :u", u=new["payee_id"])
        if payee and payee["is_woman"]:
            out.append(("revenue_women_fcfa", new["amount_fcfa"]))
    return out


def process_changes() -> int:
    """Lit le journal entre le dernier curseur et le plus ancien identifiant de transaction encore actif.

    Toute transaction d'identifiant inférieur à ce seuil est terminée : aucune ligne validée en retard
    ne peut être oubliée, et chaque ligne n'est comptée qu'une fois.
    """
    with transaction() as conn:
        run(conn, "INSERT INTO cdc_cursors (consumer) VALUES (:c) ON CONFLICT DO NOTHING", c=CONSUMER)
        cursor = one(conn, "SELECT last_xid FROM cdc_cursors WHERE consumer = :c FOR UPDATE", c=CONSUMER)["last_xid"]
        # Seuil lu APRÈS le verrou : deux lecteurs simultanés ne peuvent pas faire reculer le curseur.
        watermark = one(conn, "SELECT pg_snapshot_xmin(pg_current_snapshot()) AS x")["x"]
        if int(str(watermark)) <= int(str(cursor)):
            return 0
        changes = rows(conn, """SELECT table_name, old_data, new_data FROM change_log
                                WHERE txid >= CAST(:a AS xid8) AND txid < CAST(:b AS xid8)
                                  AND table_name IN ('waste_lots', 'orders', 'payments') AND op = 'UPDATE'
                                ORDER BY seq""", a=str(cursor), b=str(watermark))
        delta: dict[str, Decimal] = {}
        for change in changes:
            for metric, value in _metrics_for(conn, change):
                delta[metric] = delta.get(metric, Decimal(0)) + Decimal(str(value or 0))
        for metric, value in delta.items():
            run(conn, "UPDATE impact_totals SET value = value + :v WHERE metric = :m", v=value, m=metric)
        run(conn, "UPDATE cdc_cursors SET last_xid = CAST(:x AS xid8) WHERE consumer = :c",
            x=str(watermark), c=CONSUMER)
        return len(changes)


def impact(user: dict | None = None) -> dict:
    processed = process_changes()
    with transaction() as conn:
        t = {r["metric"]: r["value"] for r in rows(conn, "SELECT metric, value FROM impact_totals")}
        soy_factor = setting(conn, "soy_substitution")[0]
        co2_waste = setting(conn, "co2_per_kg_waste")[0]
        co2_soy = setting(conn, "co2_per_kg_soy")[0]
        mine = None
        if user:
            mine = one(conn, """
                SELECT coalesce(sum(amount_fcfa) FILTER (WHERE payee_id = :u AND status = 'settled'), 0) AS received,
                       coalesce(sum(amount_fcfa) FILTER (WHERE payee_id = :u AND status = 'due'), 0) AS pending
                FROM payments""", u=user["id"])
            mine["waste_kg"] = one(conn, """
                SELECT coalesce(sum(l.weight_kg), 0) AS kg FROM waste_lots l JOIN waste_offers o ON o.id = l.offer_id
                WHERE l.status IN ('received', 'used', 'recalled') AND l.quality IS NOT NULL
                  AND (o.producer_id = :u OR l.farm_id = :u OR l.collector_id = :u)""", u=user["id"])["kg"]
    soy = t["flour_delivered_kg"] * soy_factor
    revenue = t["revenue_waste_fcfa"] + t["revenue_collection_fcfa"]
    return {
        "waste_tonnes": round(t["waste_received_kg"] / 1000, 2),
        "flour_delivered_kg": t["flour_delivered_kg"],
        "soy_avoided_kg": round(soy, 1),
        "co2_avoided_kg": round(t["waste_received_kg"] * co2_waste + soy * co2_soy, 1),
        "revenue_paid_fcfa": revenue,
        "flour_sales_fcfa": t["revenue_flour_fcfa"],
        "women_share_pct": round(100 * t["revenue_women_fcfa"] / revenue, 1) if revenue else None,
        "changes_processed": processed,
        "mine": mine,
        "note": "Facteurs de soja et de CO2 indicatifs, réglables dans les paramètres.",
    }
