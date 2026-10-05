"""SQLite schema, persistence, and transaction behavior."""

# standard imports
from pathlib import Path

# lib imports
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import inspect, text

# local imports
from common import definitions
from plex.servers import ServerRecord
from themerr import storage


def _dashboard() -> dict:
    """Return one complete dashboard snapshot."""
    return {'1': {
        'key': 1, 'title': 'Movies', 'agent': 'tv.plex.agents.movie', 'type': 'movie',
        'media_count': 1, 'media_percent_complete': 0, 'collection_count': 0,
        'collection_percent_complete': 0, 'collections_enabled': True, 'total_count': 1,
        'items': [{
            'rating_key': '42', 'title': 'Example', 'type': 'movie', 'year': 2020,
            'agent': 'tv.plex.agents.movie', 'database': 'imdb', 'database_type': 'movies',
            'database_id': None, 'issue_action': 'add', 'issue_url': None,
            'theme': False, 'theme_provider': None, 'theme_status': 'missing',
        }],
    }}


def test_state_survives_restart(configured):
    storage.replace_dashboard(_dashboard())
    storage.set_error(42, 'Video unavailable')
    storage.save_tracking(42, 'movie', {
        'youtube_theme_url': 'https://youtube.example', 'uploaded_theme_key': 'upload://themes/verified',
        'audio_codec': 'mp4a', 'mp4a_available': True, 'audio_sha256': 'verified-digest',
    })
    storage.save_credentials({'client_id': 'abc'})
    storage.close()
    assert storage.get_dashboard()['1']['items'][0]['rating_key'] == '42'
    assert storage.get_errors() == {'42': 'Video unavailable'}
    assert storage.get_credentials() == {'client_id': 'abc'}
    assert storage.get_tracking(42) == {
        'youtube_theme_url': 'https://youtube.example', 'uploaded_theme_key': 'upload://themes/verified',
        'audio_codec': 'mp4a', 'mp4a_available': True, 'audio_sha256': 'verified-digest',
    }
    storage.set_error(42, None)
    storage.close()
    assert storage.get_errors() == {}


def _migration_config(connection):
    migration = Config()
    migration.set_main_option('script_location', str(Path(storage.__file__).parent / 'migrations'))
    migration.attributes['connection'] = connection
    return migration


def test_initial_migration_creates_complete_model_schema(configured):
    with storage.engine().connect() as connection:
        script = ScriptDirectory.from_config(_migration_config(connection))
        revisions = list(script.walk_revisions())
        assert len(revisions) == 2
        assert revisions[-1].down_revision is None
        assert len(revisions[0].revision) == 12
        assert int(revisions[0].revision, 16) >= 0
        revision = connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
        assert revision == script.get_current_head()
        context = MigrationContext.configure(connection, opts={'compare_server_default': True})
        assert compare_metadata(context, ServerRecord.metadata) == []


def test_initial_migration_can_downgrade_and_rebuild(configured):
    with storage.engine().begin() as connection:
        migration = _migration_config(connection)
        command.downgrade(migration, 'base')
        assert inspect(connection).get_table_names() == ['alembic_version']
        command.upgrade(migration, 'head')
        assert compare_metadata(MigrationContext.configure(connection), ServerRecord.metadata) == []


def test_jellyfin_migration_preserves_plex_dashboard_and_theme_history(configured):
    storage.replace_dashboard(_dashboard())
    storage.save_tracking(42, 'movie', {'youtube_theme_url': 'source', 'audio_sha256': 'digest'})
    with storage.engine().begin() as connection:
        migration = _migration_config(connection)
        command.downgrade(migration, 'c78c7a5bd3a3')
        assert connection.execute(text('SELECT key FROM library_sections')).scalar_one() == 1
        command.upgrade(migration, 'head')
        assert connection.execute(text('SELECT key FROM library_sections')).scalar_one() == '1'
        assert connection.execute(text('PRAGMA foreign_key_check')).all() == []
    assert storage.get_dashboard()['1']['items'][0]['rating_key'] == '42'
    assert storage.get_tracking(42)['audio_sha256'] == 'digest'


def test_opaque_library_and_item_keys_remain_scoped(configured):
    snapshot = _dashboard()['1']
    with storage.server_scope('jellyfin:server'):
        section = {**snapshot, 'key': 'a' * 32, 'items': [{**snapshot['items'][0], 'rating_key': 'b' * 32}]}
        storage.replace_dashboard({'a' * 32: section})
        assert storage.get_dashboard()['a' * 32]['items'][0]['rating_key'] == 'b' * 32
    assert storage.get_dashboard() is None


def test_dashboard_replacement_is_atomic(configured):
    storage.replace_dashboard(_dashboard())
    broken = _dashboard()
    del broken['1']['items'][0]['rating_key']
    with pytest.raises(KeyError):
        storage.replace_dashboard(broken)
    assert storage.get_dashboard()['1']['items'][0]['title'] == 'Example'


def test_theme_upload_updates_dashboard_row_and_progress(configured):
    snapshot = _dashboard()
    section = snapshot['1']
    section['media_count'] = 2
    section['collection_count'] = 1
    section['total_count'] = 3
    section['items'].append({
        **section['items'][0], 'rating_key': '43', 'title': 'Second movie',
    })
    section['items'].append({
        **section['items'][0], 'rating_key': '44', 'title': 'Collection', 'type': 'collection',
    })
    storage.replace_dashboard(snapshot)

    storage.mark_dashboard_theme_uploaded(42, 'themerr')
    storage.mark_dashboard_theme_uploaded(42, 'themerr')
    data = storage.get_dashboard()['1']
    assert data['media_percent_complete'] == 50
    assert data['collection_percent_complete'] == 0
    assert data['items'][0]['theme'] is True
    assert data['items'][0]['theme_status'] == 'complete'
    assert data['items'][0]['theme_provider'] == 'themerr'

    storage.mark_dashboard_theme_uploaded(44, 'uploaded')
    data = storage.get_dashboard()['1']
    assert data['media_percent_complete'] == 50
    assert data['collection_percent_complete'] == 100
    assert data['items'][2]['theme_provider'] == 'uploaded'


def test_dashboard_refresh_retains_upload_completed_during_scan(configured):
    snapshot = _dashboard()
    storage.replace_dashboard(snapshot)
    scan_revision = storage.dashboard_revision()
    storage.mark_dashboard_theme_uploaded(42, 'themerr')

    storage.replace_dashboard(snapshot, since_revision=scan_revision)

    data = storage.get_dashboard()['1']
    assert data['items'][0]['theme_status'] == 'complete'
    assert data['items'][0]['theme_provider'] == 'themerr'
    assert data['media_percent_complete'] == 100


def test_database_uses_active_config_directory(configured, tmp_path, monkeypatch):
    monkeypatch.setattr(definitions.Paths, 'CONFIG_DIR', str(tmp_path / 'inactive'))

    storage.set_error(42, 'Video unavailable')
    storage.close()
    assert storage.get_errors() == {'42': 'Video unavailable'}
    assert (tmp_path / definitions.Files.DATABASE).is_file()
    assert not (tmp_path / 'inactive').exists()
