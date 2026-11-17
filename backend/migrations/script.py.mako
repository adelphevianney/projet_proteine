"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
"""
from alembic import op

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}


def upgrade():
    pass


def downgrade():
    raise NotImplementedError("les migrations ne se défont pas : aucune donnée n'est supprimée")
