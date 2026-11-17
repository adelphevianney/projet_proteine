"""Alembic : le schéma est écrit en SQL (sql/*.sql), chaque migration l'applique dans une transaction."""
from alembic import context
from sqlalchemy import create_engine

from app.config import settings

engine = create_engine(settings.database_url)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=None, transaction_per_migration=True)
    with context.begin_transaction():
        context.run_migrations()
