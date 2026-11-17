"""Parcours complet d'un lot, de l'offre au paiement, et règles de paiement."""
from .conftest import make_actor
from .helpers import chain_to_received


def test_parcours_complet(client):
    producer, farm, collector, lot = chain_to_received(client, weight=300)
    assert lot["status"] == "received" and lot["code"].startswith("DL-")

    pays = {(p["kind"], p["payer_id"]): p for p in farm.get("/payments").json()["items"]}
    assert pays[("collection", farm.id)]["amount_fcfa"] == 300 * 5
    assert pays[("waste", farm.id)]["amount_fcfa"] == 300 * 15
    commission = [p for p in producer.get("/payments").json()["items"] if p["kind"] == "commission"]
    assert commission[0]["amount_fcfa"] == round(300 * 15 * 0.05)

    batch = farm.post("/flour-batches", {"source_lot_ids": [lot["id"]], "quantity_kg": 60, "price_per_kg": 350})
    assert batch.status_code == 200, batch.text
    batch = batch.json()
    assert batch["source_codes"] == [lot["code"]]

    breeder = make_actor(client, "breeder", "Élevage Bamba", lat=5.33, lng=-4.05)
    available = breeder.get("/flour-batches/available").json()
    assert available[0]["code"] == batch["code"]
    order = breeder.post("/orders", {"flour_batch_id": batch["id"], "quantity_kg": 20})
    assert order.status_code == 200, order.text
    order = order.json()
    assert order["total_fcfa"] == 20 * 350
    assert farm.post(f"/orders/{order['id']}/deliver").status_code == 200

    flour_payment = next(p for p in breeder.get("/payments").json()["items"] if p["kind"] == "flour")
    res = breeder.post(f"/payments/{flour_payment['id']}/confirm", {"reference": "OM-123456"})
    assert res.status_code == 200 and res.json()["status"] == "settled"
    # Double envoi : sans effet, pas d'erreur
    assert breeder.post(f"/payments/{flour_payment['id']}/confirm", {"reference": "OM-123456"}).status_code == 200
    # Seul le payeur confirme
    waste_payment = next(p for p in farm.get("/payments").json()["items"] if p["kind"] == "waste")
    assert producer.post(f"/payments/{waste_payment['id']}/confirm", {"reference": "X-0001"}).status_code == 403
    assert farm.post(f"/payments/{waste_payment['id']}/confirm", {"reference": "OM-777"}).status_code == 200

    trace = client.get(f"/api/v1/trace/{batch['code']}").json()
    assert trace["sources"][0]["code"] == lot["code"]
    assert trace["sources"][0]["received_at"] is not None
    assert "Awa" not in str(trace)  # pas de données personnelles

    impact = breeder.get("/impact").json()
    assert impact["waste_tonnes"] == 0.3
    assert float(impact["flour_delivered_kg"]) == 20
    assert impact["revenue_paid_fcfa"] == 300 * 15
    assert impact["women_share_pct"] == 100.0
    # Relire l'impact ne recompte rien
    assert breeder.get("/impact").json()["revenue_paid_fcfa"] == 300 * 15

    notes = [n["kind"] for n in producer.get("/notifications").json()]
    assert {"reservation", "collecte", "reception"} <= set(notes)


def test_lot_degrade_et_rejete(client):
    producer, farm, collector, lot = chain_to_received(client, weight=200, quality="degrade")
    waste = next(p for p in farm.get("/payments").json()["items"] if p["kind"] == "waste")
    assert waste["amount_fcfa"] == round(200 * 15 * 0.7)

    _, _, _, rejected = chain_to_received(client, weight=100, quality="rejete", producer=producer, farm=farm,
                                          collector=collector)
    assert rejected["status"] == "rejected"
    kinds = [p["kind"] for p in farm.get("/payments").json()["items"] if p["ref_code"] == rejected["code"]]
    assert kinds == ["collection"]  # le collecteur est payé, pas le déchet rejeté


def test_ferme_non_validee_bloquee(client):
    farm = make_actor(client, "farm", validate=False)
    assert farm.data["status"] == "pending"
    assert farm.get("/offers/nearby").status_code == 403


def test_comprehension_texte_libre(client):
    p = client.post("/api/v1/offers/parse", json={"text": "300 kg de manioc par semaine"}).json()
    assert p == {"quantity_kg": 300.0, "waste_type_id": "manioc", "frequency": "hebdomadaire"}
    p = client.post("/api/v1/offers/parse", json={"text": "2 tonnes de cabosses chaque mois"}).json()
    assert p["quantity_kg"] == 2000.0 and p["waste_type_id"] == "cacao" and p["frequency"] == "mensuelle"


def test_offres_proches_et_tournee(client):
    producer = make_actor(client, "producer")
    farm = make_actor(client, "farm", lat=5.36, lng=-4.0)
    near = producer.post("/offers", {"waste_type_id": "cajou", "quantity_kg": 100, "lat": 5.37, "lng": -4.0}).json()
    far = producer.post("/offers", {"waste_type_id": "cacao", "quantity_kg": 100, "lat": 5.6, "lng": -4.0}).json()
    listed = farm.get("/offers/nearby?km=100").json()
    assert [o["id"] for o in listed] == [near["id"], far["id"]]
    collector = make_actor(client, "collector", lat=5.36, lng=-4.0)
    farm.post(f"/offers/{far['id']}/reserve")
    farm.post(f"/offers/{near['id']}/reserve")
    tour = collector.get("/tour").json()
    assert [s["waste_type_id"] for s in tour["stops"]] == ["cajou", "cacao"]
    assert tour["total_km"] > 20
