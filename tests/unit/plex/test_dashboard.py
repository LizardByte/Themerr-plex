"""Dashboard cache built from fake Plex sections and ThemerrDB lookups."""

# standard imports
from types import SimpleNamespace
from unittest.mock import Mock

# local imports
from plex.backend import PlexMediaServer
from plex import dashboard as cache
from themerr import storage


def test_cache_without_plex(monkeypatch):
    monkeypatch.setattr(cache, 'setup_plexapi', lambda: None)
    save = Mock()
    monkeypatch.setattr(cache.storage, 'replace_dashboard', save)
    cache._cache_server()
    save.assert_not_called()


def test_cache_data(configured, item, tmp_path, monkeypatch):
    section = SimpleNamespace(
        agent='tv.plex.agents.movie', key=1, title='Movies', type='movie',
    )
    section.all = Mock(side_effect=lambda **kwargs: [item] if not kwargs else [])
    section.collections = Mock(return_value=[])
    unsupported = SimpleNamespace(agent='unsupported')
    plex = SimpleNamespace(library=SimpleNamespace(sections=lambda: [unsupported, section]))
    monkeypatch.setattr(cache, 'setup_plexapi', lambda: plex)
    monkeypatch.setattr(cache.themerr_db, 'update_cache', Mock())
    monkeypatch.setattr(cache.themerr_db, 'item_exists', lambda **_: False)
    monkeypatch.setattr(cache, 'get_database_info', lambda **_: ('movies', 'themoviedb', section.agent, '1'))
    monkeypatch.setattr(cache.general, 'get_theme_provider', lambda **_: None)
    configured['Themerr']['BOOL_PLEX_COLLECTION_SUPPORT'] = False

    cache._cache_server()

    data = storage.get_dashboard()
    assert data['1']['media_count'] == 1
    assert data['1']['items'][0]['theme_status'] == 'missing'
    assert data['1']['items'][0]['issue_action'] == 'add'
    assert section.collections.call_count == 0


def test_cache_item_converts_imdb_id_and_marks_existing_theme(item, monkeypatch):
    item.theme = 'existing theme'
    monkeypatch.setattr(cache, 'get_database_info', lambda **_: (
        'movies', 'imdb', 'com.plexapp.agents.imdb', 'tt42',
    ))
    monkeypatch.setattr(cache.tmdb, 'get_tmdb_id_from_external_id', lambda **_: 99)
    monkeypatch.setattr(cache.themerr_db, 'item_exists', lambda **_: True)
    monkeypatch.setattr(cache.general, 'get_theme_provider', lambda **_: 'plex')

    data = cache._cache_item(item)

    assert data['database_id'] == 99
    assert data['issue_action'] == 'edit'
    assert data['theme_status'] == 'complete'
    assert data['theme_provider'] == 'plex'
    assert 'Example+%282020%29' in data['issue_url']


def test_cache_distinguishes_external_id_from_unresolved_id(item, monkeypatch):
    monkeypatch.setattr(cache, 'get_database_info', lambda **_: (
        'movies', 'imdb', 'tv.plex.agents.movie', 'tt0437863',
    ))
    monkeypatch.setattr(cache, 'get_external_id', lambda _: ('imdb', 'tt0437863'))
    monkeypatch.setattr(cache.tmdb, 'get_tmdb_id_from_external_id', lambda **_: None)
    monkeypatch.setattr(cache.themerr_db, 'item_exists', lambda **_: False)
    monkeypatch.setattr(cache.general, 'get_theme_provider', lambda **_: None)
    data = cache._cache_item(item)
    assert data['database_id'] is None
    assert data['source_id'] == 'tt0437863'
    assert data['theme_status'] == 'missing'
    assert cache._cache_item(item, errors={'42': 'Video unavailable'})['theme_status'] == 'failed'

    monkeypatch.setattr(cache, 'get_database_info', lambda **_: (
        'movie_collections', 'themoviedb', 'tv.plex.agents.movie', None,
    ))
    monkeypatch.setattr(cache, 'get_external_id', lambda _: (None, None))
    item.type = 'collection'
    data = cache._cache_item(item)
    assert data['theme_status'] == 'unresolved'
    assert data['source_id'] is None


def test_legacy_section_keeps_modern_matched_media(item):
    legacy_item = SimpleNamespace(guid='com.plexapp.agents.imdb://tt123')
    section = SimpleNamespace(agent='legacy.agent', type='movie', all=Mock(return_value=[legacy_item, item]))

    assert cache._section_media_items(section) == [item]


def test_cache_data_includes_modern_item_in_legacy_section(configured, item, tmp_path, monkeypatch):
    legacy_item = SimpleNamespace(guid='com.plexapp.agents.imdb://tt123')
    section = SimpleNamespace(agent='legacy.agent', type='movie', key=7, title='Mixed Movies')
    section.all = Mock(return_value=[legacy_item, item])
    plex = SimpleNamespace(library=SimpleNamespace(sections=lambda: [section]))
    monkeypatch.setattr(cache, 'setup_plexapi', lambda: plex)
    monkeypatch.setattr(cache.themerr_db, 'update_cache', Mock())
    monkeypatch.setattr(cache.themerr_db, 'item_exists', lambda **_: False)
    monkeypatch.setattr(cache, 'get_database_info', lambda **_: ('movies', 'themoviedb', section.agent, '1'))
    monkeypatch.setattr(cache.general, 'get_theme_provider', lambda **_: None)
    cache._cache_server()

    data = storage.get_dashboard()
    assert data['7']['media_count'] == 1
    assert len(data['7']['items']) == 1


def test_cache_deduplicates_plex_results_and_preserves_shared_library_entries(configured, item, monkeypatch):
    item.theme = 'existing theme'
    other_movie = SimpleNamespace(**{
        **vars(item),
        'ratingKey': '43',
        'theme': None,
    })
    collection = SimpleNamespace(**{
        **vars(item),
        'ratingKey': 44,
        'type': 'collection',
        'title': 'Collection',
    })
    other_collection = SimpleNamespace(**{
        **vars(collection),
        'ratingKey': '45',
        'theme': None,
    })
    repeated_movie = SimpleNamespace(**{**vars(item), 'ratingKey': str(item.ratingKey)})
    sections = []
    for key in (
        1,
        2,
    ):
        section = SimpleNamespace(
            agent='tv.plex.agents.movie',
            key=key,
            title=f'Movies {key}',
            type='movie',
        )
        section.all = Mock(side_effect=lambda **kwargs: [
            item,
            repeated_movie,
        ] if kwargs else [
            item,
            repeated_movie,
            other_movie,
        ])
        section.collections = Mock(side_effect=lambda **kwargs: [
            collection,
            collection,
        ] if kwargs else [
            collection,
            collection,
            other_collection,
        ])
        sections.append(section)
    plex = SimpleNamespace(library=SimpleNamespace(sections=lambda: sections))
    monkeypatch.setattr(cache, 'setup_plexapi', lambda: plex)
    monkeypatch.setattr(cache.themerr_db, 'update_cache', Mock())
    monkeypatch.setattr(cache.themerr_db, 'item_exists', lambda **_: True)
    monkeypatch.setattr(cache, 'get_database_info', lambda item: (
        'movie_collections' if item.type == 'collection' else 'movies',
        'themoviedb',
        'tv.plex.agents.movie',
        '1',
    ))
    monkeypatch.setattr(cache, 'get_external_id', lambda _: (
        'themoviedb',
        '1',
    ))
    monkeypatch.setattr(cache.general, 'get_theme_provider', lambda item: 'uploaded' if item.theme else None)
    configured['Themerr']['BOOL_PLEX_COLLECTION_SUPPORT'] = True
    adapter = PlexMediaServer('plex-server')

    for _ in range(2):
        assert adapter.cache_dashboard()
        with storage.server_scope('plex-server'):
            data = storage.get_dashboard()
        assert set(data) == {
            '1',
            '2',
        }
        for section in data.values():
            assert [row['rating_key'] for row in section['items']] == [
                '42',
                '43',
                '44',
                '45',
            ]
            assert section['media_count'] == 2
            assert section['collection_count'] == 2
            assert section['total_count'] == 4
            assert section['media_percent_complete'] == 50
            assert section['collection_percent_complete'] == 50

    with storage.server_scope('plex-server'):
        storage.mark_dashboard_theme_uploaded(43, 'themerr')
        storage.mark_dashboard_theme_uploaded(45, 'themerr')
        for section in storage.get_dashboard().values():
            assert section['media_percent_complete'] == 100
            assert section['collection_percent_complete'] == 100
            assert section['items'][1]['theme_provider'] == 'themerr'
            assert section['items'][3]['theme_provider'] == 'themerr'
    assert storage.get_dashboard() is None
