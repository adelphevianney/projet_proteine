"""Données de démonstration : acteurs fictifs autour d'Abidjan, de Bouaké et d'Agboville.

Les données passent par les services métier, donc par les mêmes transactions et garde-fous que l'application.
Lancement : python -m seed.demo   (ne fait rien si la base contient déjà des utilisateurs)
Connexion : numéro de téléphone ci-dessous, le code s'affiche à l'écran en mode prototype.
"""
from app.db import one, transaction
from app.domain import accounts, community, flour, lots, offers, orders, payments
from app.security import USER_SQL, create_token, decode_token

ACTORS = [
    # téléphone, nom, rôle, lat, lng, commune, femme
    ("+2250700000000", "Équipe plateforme", "admin", 5.345, -4.024, "Plateau", False),
    ("+2250700000001", "Awa Koné (attiéké)", "producer", 5.336, -4.074, "Yopougon", True),
    ("+2250700000002", "Coopérative Cajou du Gbêkê", "producer", 7.700, -5.020, "Bouaké", False),
    ("+2250700000003", "Adjoua Kouassi (marché)", "producer", 5.354, -4.023, "Adjamé", True),
    ("+2250700000004", "Konan Yao (planteur cacao)", "producer", 5.928, -4.213, "Agboville", False),
    ("+2250700000011", "BioLarve Songon", "farm", 5.300, -4.260, "Songon", False),
    ("+2250700000012", "Insecta Bouaké", "farm", 7.690, -5.030, "Bouaké", True),
    ("+2250700000013", "Nouvelle ferme Dabou", "farm", 5.325, -4.377, "Dabou", False),
    ("+2250700000021", "Koffi (tricycle)", "collector", 5.340, -4.060, "Yopougon", False),
    ("+2250700000022", "Moussa (moto)", "collector", 7.695, -5.025, "Bouaké", False),
    ("+2250700000031", "Élevage Bamba (poulets)", "breeder", 5.494, -4.052, "Anyama", False),
    ("+2250700000032", "Pisciculture de la Lagune", "breeder", 5.310, -4.240, "Songon", True),
    ("+2250700000033", "Porcherie Yao", "breeder", 7.680, -5.040, "Bouaké", False),
]


def _user(user_id):
    with transaction() as conn:
        return one(conn, USER_SQL, id=user_id)


def main():
    with transaction() as conn:
        if one(conn, "SELECT count(*) AS n FROM users")["n"]:
            print("Base déjà remplie : rien à faire.")
            return

    u = {}
    for phone, name, role, lat, lng, commune, woman in ACTORS:
        # Le rôle administrateur vient de ADMIN_PHONES : on s'inscrit avec un rôle ordinaire, la configuration tranche.
        res = accounts.signup(create_token(phone, purpose="signup", hours=1), name,
                              "producer" if role == "admin" else role, lat, lng, commune, woman)
        u[phone[-2:]] = decode_token(res["token"])["sub"]
    admin = _user(u["00"])
    for key in ("11", "12", "21", "22"):  # la ferme de Dabou (13) reste en attente de validation
        accounts.set_status(admin, u[key], "active")
    U = {k: _user(v) for k, v in u.items()}
    awa, coop, adjoua, konan = U["01"], U["02"], U["03"], U["04"]
    songon, insecta, koffi, moussa = U["11"], U["12"], U["21"], U["22"]
    bamba, lagune, yao = U["31"], U["32"], U["33"]

    def offer(p, t, kg, lat, lng, freq="hebdomadaire", desc=None):
        return offers.create(p, {"waste_type_id": t, "quantity_kg": kg, "lat": lat, "lng": lng,
                                 "frequency": freq, "description": desc})

    o_a = offer(awa, "manioc", 320, 5.336, -4.074, desc="Épluchures de manioc de la production d'attiéké")
    o_b = offer(adjoua, "marche", 150, 5.354, -4.023, "quotidienne", "Invendus de fruits et légumes")
    o_c = offer(coop, "cajou", 500, 7.700, -5.020, "ponctuelle", "Pommes de cajou après récolte des noix")
    o_d = offer(awa, "manioc", 280, 5.336, -4.074)
    o_e = offer(konan, "cacao", 800, 5.928, -4.213, "mensuelle", "Cabosses après écabossage")
    offer(adjoua, "marche", 120, 5.354, -4.023, "quotidienne")
    offer(coop, "cajou", 350, 7.705, -5.010, "ponctuelle")

    # Lot A : parcours complet, conforme
    a = offers.reserve(songon, o_a["id"])
    lots.collect(koffi, a["lot_id"], 310)
    lots.receive(songon, a["lot_id"], "conforme")
    # Lot B : dégradé (prix réduit de 30 %)
    b = offers.reserve(songon, o_b["id"])
    lots.collect(koffi, b["lot_id"], 140)
    lots.receive(songon, b["lot_id"], "degrade")
    # Lot C : Bouaké
    c = offers.reserve(insecta, o_c["id"])
    lots.collect(moussa, c["lot_id"], 480)
    lots.receive(insecta, c["lot_id"], "conforme")
    # Lots D et E : réservés, dans la tournée de Koffi
    offers.reserve(songon, o_d["id"])
    offers.reserve(songon, o_e["id"])

    fb1 = flour.declare(songon, [a["lot_id"], b["lot_id"]], 90, 350)
    fb2 = flour.declare(insecta, [c["lot_id"]], 95, 330)

    o1 = orders.create(bamba, fb1["id"], 30, "seed-bamba-1")
    orders.deliver(songon, o1["id"])
    orders.create(lagune, fb1["id"], 20, "seed-lagune-1")
    o3 = orders.create(yao, fb2["id"], 40, "seed-yao-1")
    orders.deliver(insecta, o3["id"])

    # Quelques paiements réglés hors plateforme, confirmés par référence
    for payer, kind, ref in ((songon, "waste", "OM-458812"), (songon, "collection", "MOMO-22871"),
                             (bamba, "flour", "WAVE-99120"), (insecta, "waste", "OM-771020")):
        due = [p for p in payments.mine(payer)["items"]
               if p["payer_id"] == payer["id"] and p["kind"] == kind and p["status"] == "due"]
        if due:
            payments.confirm(payer, due[0]["id"], ref)

    for breeder, price in ((bamba, 470), (lagune, 450), (yao, 490)):
        community.report_price(breeder, "tourteau_soja", price, breeder["commune"])
    community.report_price(bamba, "mais", 210, "Anyama")
    community.report_price(yao, "mais", 190, "Bouaké")
    community.add_herd(bamba, "poulet_croissance", "Bande de novembre", 500)
    community.add_herd(lagune, "tilapia", "Cages lagune", 3000)
    community.add_herd(yao, "porc_croissance", "Porcs en croissance", 40)
    community.open_dispute(adjoua, "Qualité contestée", "Mon lot a été classé dégradé, il était frais le matin.",
                           None)
    # Awa change de site : nouvelle version SCD2, l'ancienne reste dans l'historique.
    accounts.update_profile(awa, {"lat": 5.345, "lng": -4.090, "commune": "Yopougon Niangon"})

    print("Données de démonstration créées.")
    for phone, name, role, *_ in ACTORS:
        print(f"  {phone}  {role:<10} {name}")
    print(f"Farine à tracer : {fb1['code']} et {fb2['code']}")


if __name__ == "__main__":
    main()
