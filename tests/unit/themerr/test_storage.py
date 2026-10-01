"""SQLite migration and transaction behavior for former JSON state."""

import json
from pathlib import Path

# lib imports
from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL

from common import definitions
from themerr import storage


def _dashboard() -> dict:
    """Return one complete legacy dashboard snapshot."""
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


def test_legacy_state_import_survives_restart(configured, tmp_path):
    dashboard_path = tmp_path / 'database_cache.json'
    errors_path = tmp_path / 'theme_errors.json'
    credentials_path = tmp_path / 'plex-auth.json'
    record_path = tmp_path / 'data' / 'Movies' / '42.json'
    record_path.parent.mkdir(parents=True)
    dashboard_path.write_text(json.dumps(_dashboard()), encoding='utf-8')
    errors_path.write_text(json.dumps({'42': 'Video unavailable'}), encoding='utf-8')
    credentials_path.write_text(json.dumps({'client_id': 'abc', 'token': 'issued'}), encoding='utf-8')
    record_path.write_text(json.dumps({'settings_hash': 'hash', 'youtube_theme_url': 'https://youtube.example',
                                       'downloaded_timestamp': 1}), encoding='utf-8')

    assert storage.get_dashboard()['1']['items'][0]['rating_key'] == '42'
    assert storage.get_errors() == {'42': 'Video unavailable'}
    assert storage.get_credentials() == {}
    assert not credentials_path.exists()
    assert storage.get_tracking(42) == {
        'youtube_theme_url': 'https://youtube.example',
    }
    with storage.engine().connect() as connection:
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '20261001_04'

    storage.save_credentials({'client_id': 'abc'})
    storage.set_error(42, None)
    storage.close()
    assert storage.get_dashboard()['1']['items'][0]['rating_key'] == '42'
    assert storage.get_credentials() == {'client_id': 'abc'}
    assert storage.get_errors() == {}
    assert all(path.exists() for path in (dashboard_path, errors_path, record_path))


def test_plaintext_token_row_is_discarded(configured):
    database = storage.engine()
    with database.begin() as connection:
        connection.execute(text("INSERT INTO app_settings (key, value) VALUES ('token', 'old-plaintext-token')"))
    storage.close()

    assert storage.get_credentials() == {}
    with storage.engine().connect() as connection:
        assert connection.execute(text("SELECT value FROM app_settings WHERE key='token'")).scalar_one_or_none() is None


def test_codec_migration_preserves_existing_uploads(configured):
    previous = create_engine(URL.create('sqlite', database=storage.database_path()))
    migration = Config()
    migration.set_main_option('script_location', str(Path(storage.__file__).parent / 'migrations'))
    with previous.begin() as connection:
        migration.attributes['connection'] = connection
        command.upgrade(migration, '20260930_01')
        connection.execute(text(
            'INSERT INTO theme_records (rating_key, item_type, settings_hash, youtube_theme_url, uploaded_theme_key) '
            "VALUES ('42', 'movie', 'former-hash', 'https://youtube.example/theme', 'upload://themes/tracked')"
        ))
    previous.dispose()

    assert storage.get_tracking(42) == {
        'youtube_theme_url': 'https://youtube.example/theme', 'uploaded_theme_key': 'upload://themes/tracked',
    }
    columns = {column['name'] for column in inspect(storage.engine()).get_columns('theme_records')}
    assert 'settings_hash' not in columns
    assert {'audio_codec', 'mp4a_available', 'audio_sha256'} <= columns


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


def test_legacy_import_uses_active_config_directory(configured, tmp_path, monkeypatch):
    monkeypatch.setattr(definitions.Paths, 'CONFIG_DIR', str(tmp_path / 'inactive'))
    (tmp_path / 'theme_errors.json').write_text(json.dumps({'42': 'Video unavailable'}), encoding='utf-8')

    assert storage.get_errors() == {'42': 'Video unavailable'}
    assert (tmp_path / 'themerr-plex.db').is_file()
