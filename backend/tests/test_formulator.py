"""Formulateur : chaque profil a une ration, plafonds respectés, ruminants sans larves."""
import pytest

from app.domain import rations


@pytest.mark.parametrize("profile", [
    "poulet_demarrage", "poulet_croissance", "pondeuse", "porc_croissance", "tilapia", "bovin_embouche",
    "ovin_embouche"])
def test_ration_respecte_besoins_et_plafonds(profile):
    out = rations.compute(None, profile, None, 100, 30)
    circ = out["circular"]
    assert abs(sum(l["share_pct"] for l in circ["lines"]) - 100) < 0.05  # arrondi à 2 décimales par ligne
    for nut, b in out["requirements"].items():
        if "min" in b:
            assert circ["nutrients"][nut] >= b["min"] - 0.01
        if "max" in b:
            assert circ["nutrients"][nut] <= b["max"] + 0.01
    prof = next(p for p in rations.profiles() if p["id"] == profile)
    for line in circ["lines"]:
        cap = prof["caps"].get(line["ingredient_id"])
        if cap is not None:
            assert line["share_pct"] <= cap * 100 + 0.01
    assert out["saving_pct"] >= 0
    if prof["family"] == "ruminant":
        assert all(l["ingredient_id"] != "farine_larves" for l in circ["lines"])


def test_prix_du_soja_change_l_economie():
    cheap = rations.compute(None, "poulet_croissance", 300, None, None)
    dear = rations.compute(None, "poulet_croissance", 600, None, None)
    assert dear["saving_pct"] > cheap["saving_pct"]
