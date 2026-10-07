"""Remember the Plex version reported by authenticated connections.

Revision ID: e71b34a5d890
Revises: d09a42b638a1
"""

# lib imports
from alembic import op
import sqlalchemy as sa

revision = 'e71b34a5d890'
down_revision = 'd09a42b638a1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add an optional version without changing saved connections or history."""
    op.add_column('plex_servers', sa.Column('version', sa.String(), nullable=True))


def downgrade() -> None:
    """Remove version metadata while preserving saved connections."""
    with op.batch_alter_table('plex_servers') as batch:
        batch.drop_column('version')
