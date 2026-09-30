"""Alembic migration environment for the Themerr SQLite database."""

from alembic import context

from themerr.storage import Base

target_metadata = Base.metadata


def run_migrations_online() -> None:
    """Run migrations on the connection supplied by the application."""
    connection = context.config.attributes['connection']
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


run_migrations_online()
