"""Create initial schema

Revision ID: c78c7a5bd3a3
Revises:
"""

# lib imports
from alembic import op
import sqlalchemy as sa

revision = 'c78c7a5bd3a3'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the schema changes."""
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )
    op.create_table(
        'library_sections',
        sa.Column('server_id', sa.String(), nullable=False),
        sa.Column('key', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('agent', sa.String(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('media_count', sa.Integer(), nullable=False),
        sa.Column('media_percent_complete', sa.Integer(), nullable=False),
        sa.Column('collection_count', sa.Integer(), nullable=False),
        sa.Column('collection_percent_complete', sa.Integer(), nullable=False),
        sa.Column('collections_enabled', sa.Boolean(), nullable=False),
        sa.Column('total_count', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('server_id', 'key'),
    )
    op.create_table(
        'plex_servers',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('url', sa.String(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('data_directory', sa.String(), nullable=False),
        sa.Column('ignored_libraries', sa.String(), nullable=False),
        sa.Column('last_refresh', sa.String(), nullable=True),
        sa.Column('last_error', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'theme_errors',
        sa.Column('server_id', sa.String(), nullable=False),
        sa.Column('rating_key', sa.String(), nullable=False),
        sa.Column('reason', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('server_id', 'rating_key'),
    )
    op.create_table(
        'theme_records',
        sa.Column('server_id', sa.String(), nullable=False),
        sa.Column('rating_key', sa.String(), nullable=False),
        sa.Column('item_type', sa.String(), nullable=False),
        sa.Column('youtube_theme_url', sa.String(), nullable=True),
        sa.Column('uploaded_theme_key', sa.String(), nullable=True),
        sa.Column('audio_codec', sa.String(), nullable=True),
        sa.Column('audio_sha256', sa.String(), nullable=True),
        sa.Column('mp4a_available', sa.Boolean(), nullable=True),
        sa.Column('art_url', sa.String(), nullable=True),
        sa.Column('poster_url', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('server_id', 'rating_key'),
    )
    op.create_table(
        'library_items',
        sa.Column('server_id', sa.String(), nullable=False),
        sa.Column('rating_key', sa.String(), nullable=False),
        sa.Column('section_key', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=True),
        sa.Column('agent', sa.String(), nullable=True),
        sa.Column('database', sa.String(), nullable=True),
        sa.Column('database_type', sa.String(), nullable=True),
        sa.Column('database_id', sa.String(), nullable=True),
        sa.Column('source_database', sa.String(), nullable=True),
        sa.Column('source_id', sa.String(), nullable=True),
        sa.Column('issue_action', sa.String(), nullable=True),
        sa.Column('issue_url', sa.String(), nullable=True),
        sa.Column('theme', sa.Boolean(), nullable=False),
        sa.Column('theme_provider', sa.String(), nullable=True),
        sa.Column('theme_status', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ['server_id', 'section_key'], ['library_sections.server_id', 'library_sections.key'],
        ),
        sa.PrimaryKeyConstraint('server_id', 'rating_key'),
    )


def downgrade() -> None:
    """Revert the schema changes."""
    op.drop_table('library_items')
    op.drop_table('theme_records')
    op.drop_table('theme_errors')
    op.drop_table('plex_servers')
    op.drop_table('library_sections')
    op.drop_table('app_settings')
