"""TMDB IDs resolved locally from the ThemerrDB index."""

from themerr import tmdb


def test_external_lookup(monkeypatch):
    calls = []
    monkeypatch.setattr(tmdb.themerr_db, 'find_movie_id_by_imdb',
                        lambda imdb_id: calls.append(('movie', imdb_id)) or 123)
    monkeypatch.setattr(tmdb.themerr_db, 'find_id_by_title',
                        lambda database_type, title: calls.append((database_type, title)) or 456)

    assert tmdb.get_tmdb_id_from_external_id('tt 1', 'imdb', 'movie') == 123
    assert tmdb.get_tmdb_id_from_external_id('999', 'tvdb', 'tv', title='Example') == 456
    assert calls == [('movie', 'tt 1'), ('tv_shows', 'Example')]
    assert tmdb.get_tmdb_id_from_external_id('x', 'invalid', 'movie') is None
    assert tmdb.get_tmdb_id_from_external_id('x', 'imdb', 'game') is None
    assert tmdb.get_tmdb_id_from_external_id('x', 'tvdb', 'tv') is None


def test_collection_lookup(monkeypatch):
    monkeypatch.setattr(tmdb.themerr_db, 'find_id_by_title',
                        lambda database_type, title: 645 if title == 'James Bond' else None)

    assert tmdb.get_tmdb_id_from_collection('James Bond') == 645
    assert tmdb.get_tmdb_id_from_collection('Unknown') is None


def test_external_api_fallback(monkeypatch):
    calls = []
    monkeypatch.setattr(tmdb.themerr_db, 'find_movie_id_by_imdb', lambda _: None)
    monkeypatch.setattr(tmdb.themerr_db, 'find_id_by_title', lambda *_: None)
    monkeypatch.delenv('TMDB_API_READ_ACCESS_TOKEN', raising=False)
    monkeypatch.setattr(tmdb.helpers, 'json_get', lambda **kwargs: calls.append(kwargs) or {
        'movie_results': [{'id': 123}], 'tv_results': [{'id': 456}],
    })

    assert tmdb.get_tmdb_id_from_external_id('tt123', 'imdb', 'movie') is None
    assert calls == []

    monkeypatch.setenv('TMDB_API_READ_ACCESS_TOKEN', 'test-token')
    assert tmdb.get_tmdb_id_from_external_id('tt123', 'imdb', 'movie') == 123
    assert tmdb.get_tmdb_id_from_external_id(42, 'tvdb', 'tv') == 456
    assert [call['url'] for call in calls] == [
        f'{tmdb.TMDB_API_URL}/find/tt123', f'{tmdb.TMDB_API_URL}/find/42',
    ]
    assert calls[0]['params'] == {'external_source': 'imdb_id'}
    assert calls[1]['params'] == {'external_source': 'tvdb_id'}
    assert calls[0]['headers']['Authorization'] == 'Bearer test-token'


def test_collection_api_fallback(monkeypatch):
    calls = []
    monkeypatch.setattr(tmdb.themerr_db, 'find_id_by_title', lambda *_: None)
    monkeypatch.setenv('TMDB_API_READ_ACCESS_TOKEN', 'test-token')
    monkeypatch.setattr(tmdb.helpers, 'json_get', lambda **kwargs: calls.append(kwargs) or {
        'results': [{'name': 'Other Collection', 'id': 1},
                    {'name': 'James Bond Collection', 'id': 645}],
    })

    assert tmdb.get_tmdb_id_from_collection('James Bond', language='en-US') == 645
    assert calls[0]['url'] == f'{tmdb.TMDB_API_URL}/search/collection'
    assert calls[0]['params'] == {'query': 'James Bond', 'language': 'en-US'}
    monkeypatch.setattr(tmdb.helpers, 'json_get', lambda **_: [])
    assert tmdb.get_tmdb_id_from_collection('Unknown') is None
