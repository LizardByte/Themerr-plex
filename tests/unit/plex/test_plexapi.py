"""Plex-facing behavior is verified with controlled server and item doubles."""

from queue import Queue
from types import SimpleNamespace
from unittest.mock import Mock

import requests

from plex import plexapi


def test_setup_plexapi(configured, monkeypatch):
    monkeypatch.setattr(plexapi, 'plex_server', None)
    configured['Plex']['PLEX_TOKEN'] = ''
    assert plexapi.setup_plexapi() is None

    configured['Plex']['PLEX_TOKEN'] = 'token'
    configured['Plex']['PLEX_URL'] = 'https://plex.example'
    server = object()
    constructor = Mock(return_value=server)
    monkeypatch.setattr(plexapi.plexapi.server, 'PlexServer', constructor)
    assert plexapi.setup_plexapi() is server
    assert plexapi.setup_plexapi() is server
    assert constructor.call_count == 1
    assert constructor.call_args.kwargs['session'].verify is False


def test_get_database_info(configured, item, monkeypatch):
    monkeypatch.setattr(plexapi, 'setup_plexapi', lambda: object())
    item.guids = [SimpleNamespace(id='imdb://tt42'), SimpleNamespace(id='tmdb://123')]
    assert plexapi.get_database_info(item) == (
        'movies', 'themoviedb', 'tv.plex.agents.movie', '123',
    )
    item.type = 'show'
    item.guids = [SimpleNamespace(id='tmdb://456')]
    assert plexapi.get_database_info(item) == (
        'tv_shows', 'themoviedb', 'tv.plex.agents.series', '456',
    )

    section = SimpleNamespace(agent='tv.plex.agents.movie', language='en')
    server = SimpleNamespace(library=SimpleNamespace(sectionByID=lambda _: section))
    monkeypatch.setattr(plexapi, 'setup_plexapi', lambda: server)
    monkeypatch.setattr(plexapi.tmdb, 'get_tmdb_id_from_collection', lambda **_: '99')
    item.type = 'collection'
    assert plexapi.get_database_info(item) == (
        'movie_collections', 'themoviedb', 'tv.plex.agents.movie', '99',
    )


def test_get_plex_item(monkeypatch):
    monkeypatch.setattr(plexapi, 'setup_plexapi', lambda: None)
    assert plexapi.get_plex_item(1) is None
    server = SimpleNamespace(fetchItem=Mock(return_value='found'))
    monkeypatch.setattr(plexapi, 'setup_plexapi', lambda: server)
    assert plexapi.get_plex_item(1) == 'found'
    server.fetchItem.assert_called_once_with(ekey=1)


def test_add_media_success(configured, item, monkeypatch):
    configured['Themerr']['BOOL_IGNORE_LOCKED_FIELDS'] = False
    configured['Themerr']['BOOL_REMOVE_UNUSED_THEMES'] = True
    monkeypatch.setattr(plexapi.general, 'get_themerr_settings_hash', lambda: 'hash')
    monkeypatch.setattr(plexapi.general, 'get_themerr_json_data', lambda **_: {})
    removed, saved, locked = Mock(), Mock(), Mock()
    monkeypatch.setattr(plexapi.general, 'remove_uploaded_media', removed)
    monkeypatch.setattr(plexapi.general, 'update_themerr_data_file', saved)
    monkeypatch.setattr(plexapi, 'change_lock_status', locked)
    monkeypatch.setattr(plexapi, 'upload_media', Mock(return_value=True))

    assert plexapi.add_media(item, 'themes', 'id', media_url='https://audio.example')
    removed.assert_called_once_with(item=item, media_type='themes')
    assert saved.call_args.kwargs['new_themerr_data'] == {
        'settings_hash': 'hash', 'youtube_theme_url': 'id',
    }
    locked.assert_called_once_with(item=item, field='theme', lock=False)


def test_add_media_skips_locked_or_unchanged(configured, item, monkeypatch):
    configured['Themerr']['BOOL_IGNORE_LOCKED_FIELDS'] = False
    monkeypatch.setattr(plexapi.general, 'get_themerr_settings_hash', lambda: 'hash')
    monkeypatch.setattr(plexapi.general, 'get_themerr_json_data', lambda **_: {
        'settings_hash': 'hash', 'youtube_theme_url': 'id',
    })
    upload = Mock()
    monkeypatch.setattr(plexapi, 'upload_media', upload)
    item.isLocked.return_value = True
    assert not plexapi.add_media(item, 'themes', 'id', media_url='https://audio.example')
    item.isLocked.return_value = False
    assert not plexapi.add_media(item, 'themes', 'id', media_url='https://audio.example')
    upload.assert_not_called()


def test_upload_media(configured, item, monkeypatch):
    configured['Themerr']['INT_PLEXAPI_UPLOAD_RETRIES_MAX'] = 1
    configured['Themerr']['INT_PLEXAPI_PLEXAPI_TIMEOUT'] = 7
    assert plexapi.upload_media(item, item.uploadTheme, url='https://audio.example')
    item.uploadTheme.assert_called_once_with(url='https://audio.example', timeout=7)
    assert plexapi.upload_media(item, item.uploadArt, filepath='poster.jpg')
    item.uploadArt.assert_called_once_with(filepath='poster.jpg')

    monkeypatch.setattr(plexapi, 'BadRequest', RuntimeError)
    monkeypatch.setattr(plexapi.time, 'sleep', Mock())
    item.uploadPoster.side_effect = RuntimeError('retry')
    assert not plexapi.upload_media(item, item.uploadPoster, url='https://poster.example')
    assert item.uploadPoster.call_count == 2


def test_change_lock_status(configured, item, monkeypatch):
    item.isLocked.side_effect = [False, True]
    assert plexapi.change_lock_status(item, 'theme', True)
    item.edit.assert_called_once_with(**{'theme.locked': 1})
    item.reload.assert_called_once_with(theme=True)

    item.isLocked.side_effect = None
    item.isLocked.return_value = True
    assert plexapi.change_lock_status(item, 'theme', True)
    assert item.edit.call_count == 1


def test_change_lock_status_timeout(item, monkeypatch):
    item.isLocked.side_effect = [False, False]
    item.edit.side_effect = requests.ReadTimeout()
    monkeypatch.setattr(plexapi.time, 'sleep', Mock())
    assert not plexapi.change_lock_status(item, 'theme', True)
    assert item.edit.call_count == 3


def test_update_missing_or_not_in_db(item, monkeypatch):
    monkeypatch.setattr(plexapi, 'get_plex_item', lambda **_: None)
    assert plexapi.update_plex_item(42) is False
    monkeypatch.setattr(plexapi, 'get_plex_item', lambda **_: item)
    monkeypatch.setattr(plexapi, 'get_database_info', lambda **_: (
        'movies', 'themoviedb', 'tv.plex.agents.movie', '42',
    ))
    monkeypatch.setattr(plexapi.themerr_db, 'item_exists', lambda **_: False)
    assert plexapi.update_plex_item(42) is False


def test_update_collection_metadata_and_theme(configured, item, monkeypatch):
    item.type = 'collection'
    item.summary = 'Old summary'
    item.editSummary = Mock()
    configured['Themerr']['BOOL_UPDATE_COLLECTION_METADATA'] = True
    configured['Themerr']['BOOL_OVERWRITE_PLEX_PROVIDED_THEMES'] = True
    monkeypatch.setattr(plexapi, 'get_plex_item', lambda **_: item)
    monkeypatch.setattr(plexapi, 'get_database_info', lambda **_: (
        'movie_collections', 'themoviedb', 'tv.plex.agents.movie', '99',
    ))
    monkeypatch.setattr(plexapi.themerr_db, 'item_exists', lambda **_: True)
    monkeypatch.setattr(plexapi.helpers, 'json_get', lambda **_: {
        'poster_path': '/poster.jpg',
        'backdrop_path': '/backdrop.jpg',
        'overview': 'New summary',
        'youtube_theme_url': 'https://youtube.example/theme',
    })
    monkeypatch.setattr(plexapi.general, 'get_themerr_settings_hash', lambda: 'hash')
    monkeypatch.setattr(plexapi.general, 'get_themerr_json_data', lambda **_: {})
    monkeypatch.setattr(plexapi, 'process_youtube', lambda **_: 'https://audio.example/theme')
    add = Mock(return_value=True)
    monkeypatch.setattr(plexapi, 'add_media', add)

    plexapi.update_plex_item(42)
    assert [call.kwargs['media_type'] for call in add.call_args_list] == ['posters', 'art', 'themes']
    item.editSummary.assert_called_once_with(summary='New summary', locked=False)


def test_listener_handler(configured, monkeypatch):
    monkeypatch.setattr(plexapi, 'q', Queue())
    configured['Themerr']['BOOL_PLEX_MOVIE_SUPPORT'] = True
    entry = {'type': 1, 'state': 5, 'identifier': 'com.plexapp.plugins.library', 'itemID': '42'}
    plexapi.plex_listener_handler({'type': 'timeline', 'TimelineEntry': [entry, entry]})
    assert plexapi.q.qsize() == 1
    assert plexapi.q.get_nowait() == 42


def test_scheduled_update(configured, item, monkeypatch):
    configured['Themerr']['BOOL_PLEX_MOVIE_SUPPORT'] = True
    configured['Themerr']['BOOL_PLEX_COLLECTION_SUPPORT'] = False
    section = SimpleNamespace(agent='tv.plex.agents.movie', type='movie')
    section.all = Mock(return_value=[item])
    section.collections = Mock(return_value=[])
    library = SimpleNamespace(sections=lambda: [section])
    monkeypatch.setattr(plexapi, 'setup_plexapi', lambda: SimpleNamespace(library=library))
    monkeypatch.setattr(plexapi.themerr_db, 'update_cache', Mock())
    monkeypatch.setattr(plexapi, 'q', Queue())
    plexapi.scheduled_update()
    assert plexapi.q.get_nowait() == 42
