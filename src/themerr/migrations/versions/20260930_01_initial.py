"""Create the initial Themerr SQLite schema.

Revision ID: 20260930_01
Revises:
"""

from alembic import op
import sqlalchemy as sa

revision = '20260930_01'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create tables for dashboard state, uploads, failures, and OAuth."""
    op.create_table(
        'library_sections',
        sa.Column('key', sa.Integer(), primary_key=True),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('agent', sa.String(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('media_count', sa.Integer(), nullable=False),
        sa.Column('media_percent_complete', sa.Integer(), nullable=False),
        sa.Column('collection_count', sa.Integer(), nullable=False),
        sa.Column('collection_percent_complete', sa.Integer(), nullable=False),
        sa.Column('collections_enabled', sa.Boolean(), nullable=False),
        sa.Column('total_count', sa.Integer(), nullable=False),
    )
    op.create_table(
        'library_items',
        sa.Column('rating_key', sa.String(), primary_key=True),
        sa.Column('section_key', sa.Integer(), sa.ForeignKey('library_sections.key'), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('year', sa.Integer()),
        sa.Column('agent', sa.String()),
        sa.Column('database', sa.String()),
        sa.Column('database_type', sa.String()),
        sa.Column('database_id', sa.String()),
        sa.Column('source_database', sa.String()),
        sa.Column('source_id', sa.String()),
        sa.Column('issue_action', sa.String()),
        sa.Column('issue_url', sa.String()),
        sa.Column('theme', sa.Boolean(), nullable=False),
        sa.Column('theme_provider', sa.String()),
        sa.Column('theme_status', sa.String(), nullable=False),
    )
    op.create_table(
        'theme_records',
        sa.Column('rating_key', sa.String(), primary_key=True),
        sa.Column('item_type', sa.String(), nullable=False),
        sa.Column('settings_hash', sa.String()),
        sa.Column('youtube_theme_url', sa.String()),
        sa.Column('uploaded_theme_key', sa.String()),
        sa.Column('art_url', sa.String()),
        sa.Column('poster_url', sa.String()),
    )
    op.create_table(
        'theme_errors',
        sa.Column('rating_key', sa.String(), primary_key=True),
        sa.Column('reason', sa.String(), nullable=False),
    )
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(), primary_key=True),
        sa.Column('value', sa.String(), nullable=False),
    )


def downgrade() -> None:
    """Drop tables created by this revision."""
    op.drop_table('app_settings')
    op.drop_table('theme_errors')
    op.drop_table('theme_records')
    op.drop_table('library_items')
    op.drop_table('library_sections')
