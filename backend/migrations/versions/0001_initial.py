"""Schéma initial et données de référence.

Revision ID: 0001
"""
from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade():
    # Curseur psycopg brut : le SQL contient des '%' (format) qui ne sont pas des paramètres.
    cursor = op.get_bind().connection.dbapi_connection.cursor()
    for name in ("0001_schema.sql", "0002_reference.sql"):
        cursor.execute((SQL_DIR / name).read_text(encoding="utf-8"))


def downgrade():
    raise NotImplementedError("les migrations ne se défont pas : aucune donnée n'est supprimée")
