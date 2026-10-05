"""Support opaque library IDs and Jellyfin connections.

Revision ID: d09a42b638a1
Revises: c78c7a5bd3a3
"""

from alembic import op
import sqlalchemy as sa

revision = 'd09a42b638a1'
down_revision = 'c78c7a5bd3a3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Preserve existing Plex state while enabling Jellyfin library identifiers."""
    with op.batch_alter_table('library_sections') as batch:
        batch.alter_column('key', existing_type=sa.Integer(), type_=sa.String(), existing_nullable=False)
    with op.batch_alter_table('library_items') as batch:
        batch.alter_column('section_key', existing_type=sa.Integer(), type_=sa.String(), existing_nullable=False)
    op.create_table(
        'jellyfin_servers',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('url', sa.String(), nullable=False),
        sa.Column('version', sa.String(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('ignored_libraries', sa.String(), nullable=False),
        sa.Column('last_refresh', sa.String()),
        sa.Column('last_error', sa.String()),
    )


def downgrade() -> None:
    """Drop Jellyfin caches before restoring Plex-only library keys."""
    for table in ('library_items', 'library_sections', 'theme_records', 'theme_errors'):
        op.execute(sa.text(f"DELETE FROM {table} WHERE server_id LIKE 'jellyfin:%'"))
    op.drop_table('jellyfin_servers')
    with op.batch_alter_table('library_items') as batch:
        batch.alter_column('section_key', existing_type=sa.String(), type_=sa.Integer(), existing_nullable=False)
    with op.batch_alter_table('library_sections') as batch:
        batch.alter_column('key', existing_type=sa.String(), type_=sa.Integer(), existing_nullable=False)
