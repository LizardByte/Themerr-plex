"""Scope Plex state by server and add the server registry."""

# lib imports
from alembic import op
import sqlalchemy as sa

revision = '20261001_03'
down_revision = '20260930_02'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Keep existing state in a legacy scope until its server is identified."""
    for table, key in (('library_sections', 'key'), ('library_items', 'rating_key'),
                       ('theme_records', 'rating_key'), ('theme_errors', 'rating_key')):
        with op.batch_alter_table(table, naming_convention={
            'pk': 'pk_%(table_name)s', 'fk': 'fk_%(table_name)s_%(column_0_name)s',
        }) as batch:
            if table == 'library_items':
                batch.drop_constraint('fk_library_items_section_key', type_='foreignkey')
            batch.add_column(sa.Column('server_id', sa.String(), nullable=False, server_default='default'))
            batch.drop_constraint('pk_' + table, type_='primary')
            batch.create_primary_key('pk_' + table, ['server_id', key])
            if table == 'library_items':
                batch.create_foreign_key('fk_library_items_section', 'library_sections',
                                         ['server_id', 'section_key'], ['server_id', 'key'])
    op.create_table('plex_servers',
                    sa.Column('id', sa.String(), primary_key=True),
                    sa.Column('name', sa.String(), nullable=False),
                    sa.Column('url', sa.String(), nullable=False),
                    sa.Column('enabled', sa.Boolean(), nullable=False),
                    sa.Column('data_directory', sa.String(), nullable=False),
                    sa.Column('ignored_libraries', sa.String(), nullable=False),
                    sa.Column('last_refresh', sa.String()),
                    sa.Column('last_error', sa.String()))


def downgrade() -> None:
    """Refuse a downgrade that could merge unrelated server data."""
    raise RuntimeError('Export server data before downgrading a multi-server database.')
