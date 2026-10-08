"""Allow a cached item to belong to multiple libraries on the same server.

Revision ID: f826a1b9c4d2
Revises: e71b34a5d890
"""

# lib imports
from alembic import op
import sqlalchemy as sa

revision = 'f826a1b9c4d2'
down_revision = 'e71b34a5d890'
branch_labels = None
depends_on = None

_PRIMARY_KEY = 'pk_library_items'
_NAMING_CONVENTION = {'pk': 'pk_%(table_name)s'}


def upgrade() -> None:
    """Include the library in the cache key while preserving existing rows."""
    with op.batch_alter_table('library_items', naming_convention=_NAMING_CONVENTION) as batch:
        batch.drop_constraint(_PRIMARY_KEY, type_='primary')
        batch.create_primary_key(_PRIMARY_KEY, [
            'server_id',
            'rating_key',
            'section_key',
        ])


def downgrade() -> None:
    """Invalidate overlapping dashboards before restoring the server-wide item key."""
    connection = op.get_bind()
    overlapping_servers = connection.execute(sa.text(
        'SELECT DISTINCT server_id FROM library_items '
        'GROUP BY server_id, rating_key HAVING COUNT(*) > 1'
    )).scalars().all()
    # Older versions cannot represent these snapshots; upload history remains intact.
    for server_id in overlapping_servers:
        for table in (
            'library_items',
            'library_sections',
        ):
            connection.execute(sa.text(f'DELETE FROM {table} WHERE server_id = :server_id'), {'server_id': server_id})
    with op.batch_alter_table('library_items', naming_convention=_NAMING_CONVENTION) as batch:
        batch.drop_constraint(_PRIMARY_KEY, type_='primary')
        batch.create_primary_key(_PRIMARY_KEY, [
            'server_id',
            'rating_key',
        ])
