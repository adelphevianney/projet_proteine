"""Formulateur : ration circulaire comparée à une ration classique, quantités pour un élevage."""
from __future__ import annotations

from psycopg.types.json import Jsonb

from ..db import one, rows, transaction
from ..errors import DomainError, not_found
from ..formulator.solver import NUTRIENTS, Infeasible, solve


def profiles() -> list[dict]:
    with transaction() as conn:
        return rows(conn, """SELECT p.id, p.family, p.name, v.requirements, v.caps, v.daily_intake_kg
                             FROM animal_profiles p
                             JOIN animal_profile_versions v ON v.profile_id = p.id AND v.is_current
                             ORDER BY p.family, p.id""")


def ingredients() -> list[dict]:
    with transaction() as conn:
        return rows(conn, """SELECT i.id, i.name, i.kind, v.price_fcfa_kg AS price, v.nutrients, v.alert
                             FROM ingredients i
                             JOIN ingredient_versions v ON v.ingredient_id = i.id AND v.is_current
                             ORDER BY i.kind, i.id""")


def _profile(profile_id: str) -> dict:
    with transaction() as conn:
        prof = one(conn, """SELECT p.id, p.name, p.family, v.version_id, v.requirements, v.caps, v.daily_intake_kg
                            FROM animal_profiles p
                            JOIN animal_profile_versions v ON v.profile_id = p.id AND v.is_current
                            WHERE p.id = :p""", p=profile_id)
    if not prof:
        raise not_found("profil d'animal inconnu")
    return prof


def _solve_both(ings: list[dict], prof: dict) -> tuple[dict, dict | None]:
    """Ration circulaire (obligatoire) et ration classique sans ingrédients locaux ni larves (si faisable)."""
    try:
        circular = solve(ings, prof["requirements"], prof["caps"])
    except Infeasible as exc:
        raise DomainError(422, str(exc)) from exc
    try:
        classic = solve(ings, prof["requirements"], prof["caps"], exclude_kinds={"local", "larves"})
    except Infeasible:
        classic = None
    return circular, classic


def _alerts(circular: dict, family: str) -> list[str]:
    alerts = [f"{l['name']} : {l['alert']}" + (" (plafond atteint)" if l["at_cap"] else "")
              for l in circular["lines"] if l["alert"]]
    if family == "ruminant":
        alerts.insert(0, "Ruminants : pas de farine de larves ; respecter les plafonds de cajou (tanins), "
                         "cacao (théobromine) et coton (gossypol), avec une transition progressive.")
    return alerts


def _quantities(circular: dict, daily_intake_kg, headcount: int, days: int, saving_fcfa_kg: float | None) -> dict:
    total = float(daily_intake_kg) * headcount * days
    flour_pct = next((l["share_pct"] for l in circular["lines"] if l["ingredient_id"] == "farine_larves"), 0)
    q = {
        "headcount": headcount, "days": days, "total_feed_kg": round(total, 1),
        "lines": [{"name": l["name"], "kg": round(total * l["share_pct"] / 100, 1)} for l in circular["lines"]],
        "flour_to_buy_kg": round(total * flour_pct / 100, 1),
        "total_cost_fcfa": round(total * circular["cost_fcfa_kg"]),
    }
    if saving_fcfa_kg is not None:
        q["total_saving_fcfa"] = round(total * saving_fcfa_kg)
    return q


def compute(user: dict | None, profile_id: str, soy_price: int | None, headcount: int | None,
            days: int | None, save: bool = False) -> dict:
    prof = _profile(profile_id)
    ings = ingredients()
    for i in ings:
        if i["id"] == "tourteau_soja" and soy_price:
            i["price"] = soy_price
    soy = next(i["price"] for i in ings if i["id"] == "tourteau_soja")
    circular, classic = _solve_both(ings, prof)

    out = {"profile": {"id": prof["id"], "name": prof["name"], "family": prof["family"]},
           "soy_price": soy, "circular": circular, "classic": classic, "nutrient_labels": NUTRIENTS,
           "requirements": prof["requirements"]}
    if classic:
        saving = classic["cost_fcfa_kg"] - circular["cost_fcfa_kg"]
        out["saving_fcfa_kg"] = round(saving, 1)
        out["saving_pct"] = round(100 * saving / classic["cost_fcfa_kg"], 1) if classic["cost_fcfa_kg"] else 0
    out["alerts"] = _alerts(circular, prof["family"])
    if headcount and days:
        out["quantities"] = _quantities(circular, prof["daily_intake_kg"], headcount, days, out.get("saving_fcfa_kg"))
    if save and user:
        with transaction(user["id"]) as conn:
            one(conn, """INSERT INTO rations (breeder_id, profile_version_id, soy_price, result)
                         VALUES (:u, :v, :s, :r) RETURNING id""",
                u=user["id"], v=prof["version_id"], s=soy, r=Jsonb(out))
    return out
