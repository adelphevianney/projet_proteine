from .conftest import make_actor


def chain_to_received(client, weight=300, quality="conforme", producer=None, farm=None, collector=None,
                      waste_type="manioc"):
    """Fait avancer un lot jusqu'à la réception. Renvoie (producteur, ferme, collecteur, lot)."""
    producer = producer or make_actor(client, "producer", "Awa", is_woman=True)
    farm = farm or make_actor(client, "farm", "Ferme Larva", lat=5.40, lng=-4.02)
    collector = collector or make_actor(client, "collector", "Koffi tricycle", lat=5.37, lng=-4.01)
    offer = producer.post("/offers", {"waste_type_id": waste_type, "quantity_kg": 320, "lat": 5.36, "lng": -4.0})
    assert offer.status_code == 200, offer.text
    res = farm.post(f"/offers/{offer.json()['id']}/reserve")
    assert res.status_code == 200, res.text
    lot_id = res.json()["lot_id"]
    assert collector.post(f"/lots/{lot_id}/collect", {"weight_kg": weight}).status_code == 200
    rec = farm.post(f"/lots/{lot_id}/receive", {"quality": quality})
    assert rec.status_code == 200, rec.text
    return producer, farm, collector, rec.json()
