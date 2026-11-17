"""SCD2 (aucune perte d'information) et capture des changements (CDC)."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import engine

from .conftest import make_actor
from .helpers import chain_to_received


def test_changement_de_position_garde_l_historique(client):
    p = make_actor(client, "producer", "Mariam")
    assert p.patch("/me", {"lat": 5.40, "lng": -4.10, "commune": "Abobo"}).status_code == 200
    assert p.patch("/me", {"name": "Mariam K."}).status_code == 200
    hist = p.get("/me/history").json()
    assert len(hist) == 3
    assert [h["is_current"] for h in hist] == [False, False, True]
    assert hist[0]["commune"] == "Yopougon" and hist[1]["commune"] == "Abobo"
    assert hist[2]["name"] == "Mariam K." and hist[2]["lat"] == pytest.approx(5.40)
    assert hist[0]["valid_to"] == hist[1]["valid_from"]  # périodes contiguës, sans chevauchement

    with pytest.raises(DBAPIError, match="suppression interdite"):
        with engine.begin() as c:
            c.execute(text("DELETE FROM user_versions WHERE user_id = :u"), {"u": p.id})
    with pytest.raises(DBAPIError, match="déjà fermée"):
        with engine.begin() as c:
            c.execute(text("UPDATE user_versions SET name = 'X' WHERE user_id = :u AND NOT is_current"), {"u": p.id})
    with pytest.raises(DBAPIError):
        with engine.begin() as c:  # deux versions courantes : refusé
            c.execute(text("""INSERT INTO user_versions (user_id, name, role, status)
                              VALUES (:u, 'Doublon', 'producer', 'active')"""), {"u": p.id})


def test_offre_versionnee_et_lot_relie_a_sa_version(client):
    producer = make_actor(client, "producer")
    offer = producer.post("/offers", {"waste_type_id": "cajou", "quantity_kg": 100, "lat": 5.36, "lng": -4.0}).json()
    producer.patch(f"/offers/{offer['id']}", {"quantity_kg": 150, "price_per_kg": 20})
    farm = make_actor(client, "farm")
    lot_id = farm.post(f"/offers/{offer['id']}/reserve").json()["lot_id"]
    hist = producer.get(f"/offers/{offer['id']}/history").json()
    assert [(float(h["quantity_kg"]), h["status"]) for h in hist] == [(100, "published"), (150, "published"),
                                                                      (150, "reserved")]
    lot = next(l for l in farm.get("/lots").json() if l["id"] == lot_id)
    assert lot["price_per_kg"] == 20
    # Une offre réservée ne se modifie plus
    assert producer.patch(f"/offers/{offer['id']}", {"quantity_kg": 10}).status_code == 409


def test_journal_lu_par_increments(client):
    p = make_actor(client, "producer")
    first = p.get("/changes").json()
    assert first["changes"], "l'inscription doit apparaître dans le journal"
    token = first["next"]
    again = p.get(f"/changes?since={token}").json()
    assert again["changes"] == []
    p.post("/offers", {"waste_type_id": "manioc", "quantity_kg": 50, "lat": 5.36, "lng": -4.0})
    new = p.get(f"/changes?since={token}").json()["changes"]
    assert {c["table_name"] for c in new} == {"waste_offers", "waste_offer_versions"}
    assert "new_data" not in new[0]  # un non-admin ne reçoit pas le contenu


def test_journal_pagine_sans_boucle(client):
    """Une page pleine reprend après le dernier numéro lu, sans relire la même page."""
    from app.domain.changes import changes_since
    p = make_actor(client, "producer")
    me = p.get("/me").json()
    token = p.get("/changes").json()["next"]
    p.post("/offers", {"waste_type_id": "manioc", "quantity_kg": 50, "lat": 5.36, "lng": -4.0})
    p.post("/offers", {"waste_type_id": "cajou", "quantity_kg": 30, "lat": 5.36, "lng": -4.0})
    seen, pages = [], 0
    while True:
        page = changes_since(me, token, limit=1)
        seen += [c["seq"] for c in page["changes"]]
        token, pages = page["next"], pages + 1
        if not page["truncated"] or pages > 20:
            break
    assert pages <= 20 and len(seen) == len(set(seen)) == 4


def test_impact_incremental(client):
    _, farm, _, lot = chain_to_received(client, weight=400)
    first = farm.get("/impact").json()
    assert first["waste_tonnes"] == 0.4 and first["changes_processed"] > 0
    second = farm.get("/impact").json()
    assert second["waste_tonnes"] == 0.4 and second["changes_processed"] == 0
