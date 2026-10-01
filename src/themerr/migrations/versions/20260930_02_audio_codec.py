"""Track the uploaded codec instead of a settings hash.

Revision ID: 20260930_02
Revises: 20260930_01
"""

# lib imports
from alembic import op
import sqlalchemy as sa

revision = '20260930_02'
down_revision = '20260930_01'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Preserve uploaded themes while replacing settings hashes with codec metadata."""
    with op.batch_alter_table('theme_records') as batch:
        batch.add_column(sa.Column('audio_codec', sa.String()))
        batch.add_column(sa.Column('mp4a_available', sa.Boolean()))
        batch.drop_column('settings_hash')


def downgrade() -> None:
    """Restore the former tracking schema."""
    with op.batch_alter_table('theme_records') as batch:
        batch.add_column(sa.Column('settings_hash', sa.String()))
        batch.drop_column('mp4a_available')
        batch.drop_column('audio_codec')
