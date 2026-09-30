"""SQLite migration and transaction behavior for former JSON state."""

import json

import pytest
from sqlalchemy import text

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
    assert storage.get_credentials() == {'client_id': 'abc', 'token': 'issued'}
    assert storage.get_tracking(42) == {
        'settings_hash': 'hash', 'youtube_theme_url': 'https://youtube.example',
    }
    with storage.engine().connect() as connection:
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '20260930_01'

    storage.save_credentials({'client_id': 'abc'})
    storage.set_error(42, None)
    storage.close()
    assert storage.get_dashboard()['1']['items'][0]['rating_key'] == '42'
    assert storage.get_credentials() == {'client_id': 'abc'}
    assert storage.get_errors() == {}
    assert all(path.exists() for path in (dashboard_path, errors_path, credentials_path, record_path))


def test_dashboard_replacement_is_atomic(configured):
    storage.replace_dashboard(_dashboard())
    broken = _dashboard()
    del broken['1']['items'][0]['rating_key']
    with pytest.raises(KeyError):
        storage.replace_dashboard(broken)
    assert storage.get_dashboard()['1']['items'][0]['title'] == 'Example'


def test_legacy_import_uses_active_config_directory(configured, tmp_path, monkeypatch):
    monkeypatch.setattr(definitions.Paths, 'CONFIG_DIR', str(tmp_path / 'inactive'))
    (tmp_path / 'theme_errors.json').write_text(json.dumps({'42': 'Video unavailable'}), encoding='utf-8')

    assert storage.get_errors() == {'42': 'Video unavailable'}
    assert (tmp_path / 'themerr-plex.db').is_file()
