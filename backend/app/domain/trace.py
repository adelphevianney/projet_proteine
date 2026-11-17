"""Traçabilité par code : de la farine aux déchets d'origine, sans données personnelles."""
from __future__ import annotations

from ..db import one, rows, transaction
from ..errors import not_found


def trace(code: str) -> dict:
    code = code.strip().upper()
    with transaction() as conn:
        if code.startswith("FB-"):
            batch = one(conn, """SELECT b.id, b.code, b.quantity_kg, b.status::text AS status, b.created_at,
                                        f.commune AS farm_commune
                                 FROM flour_batches b JOIN users_current f ON f.id = b.farm_id
                                 WHERE b.code = :c""", c=code)
            if not batch:
                raise not_found("code inconnu")
            sources = rows(conn, """
                SELECT w.code, t.name AS waste_type, t.risk, w.weight_kg, w.quality::text AS quality,
                       w.status::text AS status, v.commune AS origin_commune,
                       (SELECT min(at) FROM status_events e WHERE e.entity = 'waste_lots' AND e.entity_id = w.id
                          AND e.to_status = 'collected') AS collected_at,
                       (SELECT min(at) FROM status_events e WHERE e.entity = 'waste_lots' AND e.entity_id = w.id
                          AND e.to_status = 'received') AS received_at
                FROM flour_batch_sources s
                JOIN waste_lots w ON w.id = s.waste_lot_id
                JOIN waste_offers o ON o.id = w.offer_id
                JOIN waste_offer_versions v ON v.version_id = w.offer_version_id
                JOIN waste_types t ON t.id = o.waste_type_id
                WHERE s.flour_batch_id = :b ORDER BY w.code""", b=batch["id"])
            batch.pop("id")
            return {"kind": "flour", "flour": batch, "sources": sources}
        if code.startswith("DL-"):
            lot = one(conn, """SELECT w.id, w.code, t.name AS waste_type, w.weight_kg, w.quality::text AS quality,
                                      w.status::text AS status, v.commune AS origin_commune, w.created_at
                               FROM waste_lots w JOIN waste_offers o ON o.id = w.offer_id
                               JOIN waste_offer_versions v ON v.version_id = w.offer_version_id
                               JOIN waste_types t ON t.id = o.waste_type_id WHERE w.code = :c""", c=code)
            if not lot:
                raise not_found("code inconnu")
            derived = rows(conn, """SELECT b.code, b.status::text AS status, b.quantity_kg, b.created_at
                                    FROM flour_batch_sources s JOIN flour_batches b ON b.id = s.flour_batch_id
                                    WHERE s.waste_lot_id = :l ORDER BY b.code""", l=lot["id"])
            events = rows(conn, """SELECT from_status, to_status, at FROM status_events
                                   WHERE entity = 'waste_lots' AND entity_id = :l ORDER BY id""", l=lot["id"])
            lot.pop("id")
            return {"kind": "waste", "lot": lot, "flour_batches": derived, "events": events}
    raise not_found("code inconnu : il commence par DL- (déchets) ou FB- (farine)")
