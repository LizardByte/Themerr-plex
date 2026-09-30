"""A standalone update path with all external services mocked."""

from unittest.mock import Mock

from plex import plexapi


def test_updates_theme_from_database(configured, item, monkeypatch):
    configured['Themerr']['BOOL_IGNORE_LOCKED_FIELDS'] = False
    configured['Themerr']['BOOL_OVERWRITE_PLEX_PROVIDED_THEMES'] = True
    monkeypatch.setattr(plexapi, 'get_plex_item', lambda **_: item)
    monkeypatch.setattr(plexapi, 'get_database_info', lambda **_: (
        'movies', 'themoviedb', 'tv.plex.agents.movie', '42',
    ))
    monkeypatch.setattr(plexapi.themerr_db, 'item_exists', lambda **_: True)
    monkeypatch.setattr(plexapi.helpers, 'json_get', lambda **_: {
        'youtube_theme_url': 'https://youtube.example/video',
    })
    monkeypatch.setattr(plexapi.general, 'get_themerr_settings_hash', lambda: 'hash')
    monkeypatch.setattr(plexapi.general, 'get_themerr_data', lambda **_: {})
    monkeypatch.setattr(plexapi, 'process_youtube', lambda **_: 'https://audio.example/stream')
    uploaded = Mock(return_value=True)
    monkeypatch.setattr(plexapi, 'add_media', uploaded)

    plexapi.update_plex_item(42)

    assert uploaded.call_count == 1
    assert uploaded.call_args.kwargs['item'] is item
    assert uploaded.call_args.kwargs['media_type'] == 'themes'
    assert uploaded.call_args.kwargs['media_url_id'] == 'https://youtube.example/video'
    assert uploaded.call_args.kwargs['media_url'] == 'https://audio.example/stream'
    assert callable(uploaded.call_args.kwargs['on_error'])
