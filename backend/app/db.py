"""Accès à PostgreSQL : une transaction par opération métier."""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator, TypeVar

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError

from .config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)

T = TypeVar("T")


@contextmanager
def transaction(actor_id: Any = None, serializable: bool = False) -> Iterator[Connection]:
    """Ouvre une transaction. L'auteur est transmis aux déclencheurs (journal, CDC)."""
    with engine.connect() as conn:
        if serializable:
            conn = conn.execution_options(isolation_level="SERIALIZABLE")
        with conn.begin():
            if actor_id is not None:
                conn.execute(text("SELECT set_config('app.actor_id', :a, true)"), {"a": str(actor_id)})
            yield conn


def run_serializable(fn: Callable[[Connection], T], actor_id: Any = None, retries: int = 5) -> T:
    """Exécute fn en SERIALIZABLE et la relance si PostgreSQL signale un conflit (40001, 40P01)."""
    for attempt in range(retries):
        try:
            with transaction(actor_id, serializable=True) as conn:
                return fn(conn)
        except DBAPIError as exc:
            code = getattr(exc.orig, "sqlstate", None)
            if code in ("40001", "40P01") and attempt < retries - 1:
                time.sleep(0.05 * (attempt + 1))
                continue
            raise
    raise RuntimeError("unreachable")


def rows(conn: Connection, sql: str, **params) -> list[dict]:
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def one(conn: Connection, sql: str, **params) -> dict | None:
    r = conn.execute(text(sql), params).mappings().first()
    return dict(r) if r else None


def run(conn: Connection, sql: str, **params) -> None:
    conn.execute(text(sql), params)
