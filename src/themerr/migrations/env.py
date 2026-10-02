"""Alembic migration environment for the Themerr SQLite database."""

# lib imports
from alembic import context

# local imports
from plex.servers import ServerRecord

target_metadata = ServerRecord.metadata


def run_migrations_online() -> None:
    """Run migrations on the connection supplied by the application."""
    connection = context.config.attributes['connection']
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


run_migrations_online()
