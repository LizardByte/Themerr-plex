"""Track complete file uploads separately from former URL uploads.

Revision ID: 20261001_04
Revises: 20261001_03
"""

# lib imports
from alembic import op
import sqlalchemy as sa

revision = '20261001_04'
down_revision = '20261001_03'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Mark existing URL uploads as needing replacement with validated audio."""
    op.add_column('theme_records', sa.Column('audio_sha256', sa.String()))


def downgrade() -> None:
    """Remove complete file upload tracking."""
    with op.batch_alter_table('theme_records') as batch:
        batch.drop_column('audio_sha256')
