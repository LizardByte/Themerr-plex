"""Tests for media paths, metadata, and provider selection."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from themerr import general


def test_metadata_and_upload_paths(configured, item, tmp_path):
    configured['Plex']['PLEX_APP_SUPPORT_PATH'] = str(tmp_path)
    expected_hash = hashlib.sha1(item.guid.encode()).hexdigest()
    metadata = Path(general._get_metadata_path(item))
    assert metadata == tmp_path / 'Metadata' / 'Movies' / expected_hash[0] / (expected_hash[1:] + '.bundle')
    assert Path(general.get_media_upload_path(item, 'themes')) == metadata / 'Uploads' / 'themes'
    with pytest.raises(ValueError):
        general.get_media_upload_path(item, 'invalid')


@pytest.mark.parametrize('agent, expected', [
    ('tv.plex.agents.movie', True), ('tv.plex.agents.series', True), ('invalid', False),
])
def test_continue_update(configured, agent, expected):
    configured['Themerr']['BOOL_PLEX_MOVIE_SUPPORT'] = True
    configured['Themerr']['BOOL_PLEX_SERIES_SUPPORT'] = True
    assert general.continue_update(agent) is expected


@pytest.mark.parametrize('provider, rating_key, expected', [
    ('local', 'x', 'user'),
    ('com.plexapp.agents.plexthememusic', 'x', 'plex'),
    (None, 'metadata://themes/tv.plex.agents.series_1', 'plex'),
    ('custom', 'x', 'custom'),
    (None, 'upload://themes/1', 'themerr'),
    (None, 'x', None),
])
def test_theme_provider(monkeypatch, item, provider, rating_key, expected):
    item.themes.return_value = [SimpleNamespace(selected=True, provider=provider, ratingKey=rating_key)]
    monkeypatch.setattr(general, 'get_themerr_data', lambda **_: {'uploaded_theme_key': rating_key})
    assert general.get_theme_provider(item) == expected


def test_uploaded_theme_without_tracking_is_inferred(monkeypatch, item):
    item.themes.return_value = [SimpleNamespace(selected=True, provider='custom',
                                                ratingKey='upload://themes/abcdef')]
    monkeypatch.setattr(general, 'get_themerr_data', lambda **_: {})
    assert general.get_theme_provider(item) == 'uploaded'


def test_legacy_plugin_tracking_record(configured, item, tmp_path):
    configured['Plex']['PLEX_APP_SUPPORT_PATH'] = str(tmp_path)
    path = Path(general._legacy_themerr_json_path(item))
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'youtube_theme_url': 'https://youtube.example/theme'}), encoding='utf-8')
    assert general.get_themerr_data(item)['youtube_theme_url'] == 'https://youtube.example/theme'


def test_no_selected_theme(item):
    assert general.get_theme_provider(item) is None
    item.themes.return_value = [SimpleNamespace(selected=False)]
    assert general.get_theme_provider(item) is None


def test_data_file_round_trip(configured, item, tmp_path):
    assert general.get_themerr_data(item) == {}
    general.update_themerr_data(item, {'youtube_theme_url': 'https://youtube.example/theme'})
    assert general.get_themerr_data(item) == {'youtube_theme_url': 'https://youtube.example/theme'}
    assert not (tmp_path / 'data').exists()


def test_settings_hash(configured):
    first = general.get_themerr_settings_hash()
    assert len(first) == 64
    configured['Themerr']['BOOL_PREFER_MP4A_CODEC'] = not configured['Themerr']['BOOL_PREFER_MP4A_CODEC']
    assert general.get_themerr_settings_hash() != first


def test_remove_uploaded_media(configured, item, tmp_path):
    configured['Plex']['PLEX_APP_SUPPORT_PATH'] = str(tmp_path)
    path = Path(general.get_media_upload_path(item, 'themes'))
    path.mkdir(parents=True)
    (path / 'old.mp3').write_bytes(b'audio')
    general.remove_uploaded_media(item, 'themes')
    assert not path.exists()
    general.remove_uploaded_media(item, 'themes')


def test_remove_error_handler():
    general.remove_uploaded_media_error_handler('remove', 'path', OSError('failure'))
