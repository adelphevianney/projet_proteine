"""Formulateur de ration au moindre coût (programmation linéaire, solveur HiGHS de SciPy).

Variables : x_i = part de l'ingrédient i dans 1 kg de ration (0 <= x_i <= plafond_i), somme = 1.
Contraintes : pour chaque nutriment, min <= somme(x_i * teneur_i) <= max.
Objectif : minimiser somme(x_i * prix_i).
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import linprog

NUTRIENTS = {"pb": "Protéines brutes (%)", "em": "Énergie (kcal/kg)", "ca": "Calcium (%)",
             "p": "Phosphore (%)", "lys": "Lysine (%)", "fibre": "Fibres (%)"}
CLASSIC_EXCLUDED_KINDS = {"local", "larves"}


class Infeasible(Exception):
    pass


def solve(ingredients: list[dict], requirements: dict, caps: dict, exclude_kinds: set[str] = frozenset()) -> dict:
    """ingredients : [{id, name, kind, price, nutrients, alert}] ; renvoie la ration la moins chère."""
    usable = [i for i in ingredients if i["kind"] not in exclude_kinds and caps.get(i["id"], 1) > 0]
    if not usable:
        raise Infeasible("aucun ingrédient utilisable")
    cost = np.array([float(i["price"]) for i in usable])
    a_ub, b_ub = [], []
    for nut, bounds in requirements.items():
        row = np.array([float(i["nutrients"].get(nut, 0)) for i in usable])
        if bounds.get("min") is not None:
            a_ub.append(-row)
            b_ub.append(-float(bounds["min"]))
        if bounds.get("max") is not None:
            a_ub.append(row)
            b_ub.append(float(bounds["max"]))
    bounds = [(0, float(caps.get(i["id"], 1))) for i in usable]
    res = linprog(cost, A_ub=np.array(a_ub) if a_ub else None, b_ub=b_ub or None,
                  A_eq=np.ones((1, len(usable))), b_eq=[1.0], bounds=bounds, method="highs")
    if res.status != 0:
        raise Infeasible("aucune ration ne couvre ces besoins avec ces ingrédients et plafonds")
    lines = []
    for ing, x in zip(usable, res.x.tolist()):
        if x > 1e-4:
            cap = caps.get(ing["id"])
            lines.append({"ingredient_id": ing["id"], "name": ing["name"], "kind": ing["kind"],
                          "share_pct": round(100 * x, 2), "price_fcfa_kg": ing["price"],
                          "alert": ing.get("alert"), "at_cap": cap is not None and x >= float(cap) - 1e-4})
    lines.sort(key=lambda r: -r["share_pct"])
    achieved = {n: round(float(sum(x * float(i["nutrients"].get(n, 0)) for i, x in zip(usable, res.x))), 2)
                for n in NUTRIENTS}
    return {"cost_fcfa_kg": round(float(res.fun), 1), "lines": lines, "nutrients": achieved}
