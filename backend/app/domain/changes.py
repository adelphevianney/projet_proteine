"""Lecture incrémentale du journal des changements pour les clients (téléphone, administration)."""
from __future__ import annotations

from ..db import one, rows, transaction

# Colonnes qui rattachent une ligne à un utilisateur.
_OWNER_KEYS = ("producer_id", "farm_id", "collector_id", "breeder_id", "payer_id", "payee_id", "user_id", "author_id")


def _parse_token(token: str | None) -> tuple[str, str | None, int]:
    """Jeton « debut » (lecture complète) ou « debut:fin:seq » (suite d'une page pleine, fenêtre figée)."""
    parts = (token or "0").split(":")
    if len(parts) == 3:
        return parts[0], parts[1], int(parts[2])
    return parts[0], None, 0


def changes_since(user: dict, since: str | None, limit: int = 500) -> dict:
    """Renvoie les changements validés depuis le jeton `since` et le jeton suivant.

    La fenêtre lue va de `since` au plus ancien identifiant de transaction encore actif : on ne lit que
    des transactions terminées, donc rien n'est oublié même si deux transactions finissent dans le désordre.
    Une page pleine renvoie un jeton qui fige cette fenêtre et reprend après le dernier numéro lu.
    """
    start, upper, after_seq = _parse_token(since)
    with transaction() as conn:
        if upper is None:
            upper = str(one(conn, "SELECT pg_snapshot_xmin(pg_current_snapshot()) AS x")["x"])
        is_admin = user["role"] == "admin"
        owner_filter = " OR ".join(f"new_data->>'{k}' = :u" for k in _OWNER_KEYS)
        items = rows(conn, f"""
            SELECT seq, txid::text AS txid, table_name, op, row_key, at
                   {", old_data, new_data, actor_id" if is_admin else ""}
            FROM change_log
            WHERE txid >= CAST(:a AS xid8) AND txid < CAST(:b AS xid8) AND seq > :after
              {"" if is_admin else f"AND ({owner_filter} OR table_name IN ('waste_offer_versions', 'flour_batches'))"}
            ORDER BY seq LIMIT :lim""", a=start, b=upper, after=after_seq, u=str(user["id"]), lim=limit)
    truncated = len(items) == limit
    nxt = f"{start}:{upper}:{items[-1]['seq']}" if truncated else upper
    return {"changes": items, "next": nxt, "truncated": truncated}
