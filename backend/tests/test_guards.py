"""Garde-fous : concurrence, stock, idempotence, retrait, transitions, paiements figés."""
import threading

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import engine

from .conftest import make_actor
from .helpers import chain_to_received


def _parallel(n, fn):
    results, barrier = [None] * n, threading.Barrier(n)

    def run(i):
        barrier.wait()
        results[i] = fn(i)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def test_deux_fermes_meme_offre(client):
    producer = make_actor(client, "producer")
    farms = [make_actor(client, "farm", f"Ferme {i}") for i in range(4)]
    offer = producer.post("/offers", {"waste_type_id": "manioc", "quantity_kg": 100, "lat": 5.36, "lng": -4.0}).json()
    codes = _parallel(4, lambda i: farms[i].post(f"/offers/{offer['id']}/reserve").status_code)
    assert sorted(codes) == [200, 409, 409, 409]
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM waste_lots")).scalar() == 1


def _flour(client, stock=100):
    producer, farm, collector, lot = chain_to_received(client)
    batch = farm.post("/flour-batches", {"source_lot_ids": [lot["id"]], "quantity_kg": stock,
                                         "price_per_kg": 300}).json()
    return farm, lot, batch


def test_commandes_simultanees_sans_survente(client):
    farm, _, batch = _flour(client, stock=100)
    breeders = [make_actor(client, "breeder", f"Éleveur {i}") for i in range(10)]
    codes = _parallel(10, lambda i: breeders[i].post("/orders", {"flour_batch_id": batch["id"],
                                                                 "quantity_kg": 15}).status_code)
    assert codes.count(200) == 6 and codes.count(409) == 4
    with engine.connect() as c:
        stock, status = c.execute(text("SELECT stock_kg, status FROM flour_batches WHERE id = :b"),
                                  {"b": batch["id"]}).one()
    assert float(stock) == 10 and status == "available"


def test_idempotence_commande(client):
    farm, _, batch = _flour(client, stock=100)
    breeder = make_actor(client, "breeder")
    h = {"Idempotency-Key": "commande-abc-1"}
    results = _parallel(3, lambda i: breeder.post("/orders", {"flour_batch_id": batch["id"], "quantity_kg": 10},
                                                  headers=h))
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    assert len({r.json()["id"] for r in results}) == 1
    with engine.connect() as c:
        assert float(c.execute(text("SELECT stock_kg FROM flour_batches")).scalar()) == 90


def test_retrait_en_cascade(client):
    farm, lot, batch = _flour(client, stock=100)
    b1, b2 = make_actor(client, "breeder", "B1"), make_actor(client, "breeder", "B2")
    o1 = b1.post("/orders", {"flour_batch_id": batch["id"], "quantity_kg": 10}).json()
    o2 = b2.post("/orders", {"flour_batch_id": batch["id"], "quantity_kg": 10}).json()
    farm.post(f"/orders/{o2['id']}/deliver")

    res = farm.post(f"/lots/{lot['id']}/recall", {"reason": "contamination suspectée"})
    assert res.status_code == 200, res.text
    assert res.json() == {"lot_code": lot["code"], "flour_batches": 1, "orders_cancelled": 1,
                          "breeders_alerted": 2}
    assert b1.get("/orders/mine").json()[0]["status"] == "recalled"
    assert b2.get("/orders/mine").json()[0]["status"] == "delivered"
    assert any(n["kind"] == "retrait" for n in b2.get("/notifications").json())
    flour_pay = [p for p in b1.get("/payments").json()["items"] if p["kind"] == "flour"]
    assert flour_pay[0]["status"] == "cancelled"
    assert b1.post("/orders", {"flour_batch_id": batch["id"], "quantity_kg": 1}).status_code == 409
    assert client.get(f"/api/v1/trace/{batch['code']}").json()["flour"]["status"] == "recalled"


def test_transition_interdite_par_la_base(client):
    _, _, _, lot = chain_to_received(client)
    with pytest.raises(DBAPIError, match="transition interdite"):
        with engine.begin() as c:
            c.execute(text("UPDATE waste_lots SET status = 'collected' WHERE id = :id"), {"id": lot["id"]})


def test_paiement_regle_fige(client):
    _, farm, _, _ = chain_to_received(client)
    pay = next(p for p in farm.get("/payments").json()["items"] if p["kind"] == "waste")
    farm.post(f"/payments/{pay['id']}/confirm", {"reference": "OM-42"})
    with pytest.raises(DBAPIError, match="non modifiable"):
        with engine.begin() as c:
            c.execute(text("UPDATE payments SET amount_fcfa = 1 WHERE id = :id"), {"id": pay["id"]})
    with pytest.raises(DBAPIError, match="suppression interdite"):
        with engine.begin() as c:
            c.execute(text("DELETE FROM payments WHERE id = :id"), {"id": pay["id"]})


def test_contraintes_check(client):
    farm, _, batch = _flour(client, stock=50)
    with pytest.raises(DBAPIError, match="check"):
        with engine.begin() as c:
            c.execute(text("UPDATE flour_batches SET stock_kg = -1 WHERE id = :id"), {"id": batch["id"]})
