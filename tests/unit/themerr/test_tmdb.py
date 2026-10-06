"""TMDB IDs resolved from ThemerrDB, Plex, and the optional TMDB API."""

# standard imports
from unittest.mock import Mock

# lib imports
import requests

# local imports
from themerr import tmdb
from plex import tmdb as proxy


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
    monkeypatch.setattr(proxy, 'query', lambda *_: {})
    monkeypatch.setattr(tmdb.themerr_db, 'find_id_by_title',
                        lambda database_type, title: 645 if title == 'James Bond' else None)

    assert tmdb.get_tmdb_id_from_collection('James Bond') == 645
    assert tmdb.get_tmdb_id_from_collection('Unknown') is None


def test_external_api_fallback(monkeypatch):
    calls = []
    monkeypatch.setattr(tmdb.themerr_db, 'find_movie_id_by_imdb', lambda _: None)
    monkeypatch.setattr(tmdb.themerr_db, 'find_id_by_title', lambda *_: None)
    monkeypatch.setattr(proxy, 'query', lambda *_: {})
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
    monkeypatch.setattr(proxy, 'query', lambda *_: {})
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


def test_plex_proxy_resolves_imdb_tvdb_and_collection(configured, monkeypatch):
    configured['Plex']['PLEX_URL'] = 'http://plex.example:32400/'
    proxy._proxy_cache.clear()
    monkeypatch.setattr(tmdb.themerr_db, 'find_movie_id_by_imdb', lambda *_: None)
    monkeypatch.setattr(tmdb.themerr_db, 'find_id_by_title', lambda *_: None)
    monkeypatch.delenv('TMDB_API_READ_ACCESS_TOKEN', raising=False)
    proxy.auth.set_token('secret-plex-token')
    calls = []

    def proxy_response(url, **kwargs):
        calls.append((url, kwargs))
        uri = kwargs['params']['uri']
        response = Mock()
        response.json.return_value = ({'movie_results': [{'id': 10005}]} if '/find/tt0497329' in uri
                                      else {'tv_results': [{'id': 48866}]} if '/find/268592' in uri
                                      else {'results': [{'name': 'James Bond Collection', 'id': 645}]})
        return response

    monkeypatch.setattr(proxy.requests, 'get', proxy_response)
    assert tmdb.get_tmdb_id_from_external_id('tt0497329', 'imdb', 'movie') == 10005
    assert tmdb.get_tmdb_id_from_external_id(268592, 'tvdb', 'tv') == 48866
    assert tmdb.get_tmdb_id_from_collection('James Bond', language='en-US') == 645
    assert len(calls) == 3
    assert all(url == 'http://plex.example:32400/services/tmdb' for url, _ in calls)
    assert all(kwargs['headers']['X-Plex-Token'] == 'secret-plex-token' for _, kwargs in calls)
    assert all(kwargs['timeout'] == proxy.PROXY_TIMEOUT for _, kwargs in calls)
    assert calls[0][1]['params']['uri'] == '/find/tt0497329?external_source=imdb_id'
    assert calls[1][1]['params']['uri'] == '/find/268592?external_source=tvdb_id'
    assert calls[2][1]['params']['uri'] == '/search/collection?query=James-Bond&language=en-US'
    assert tmdb.get_tmdb_id_from_external_id('tt0497329', 'imdb', 'movie') == 10005
    assert len(calls) == 3  # Successful proxy responses are cached in memory.


def test_plex_proxy_failure_falls_back_to_tmdb(configured, monkeypatch):
    configured['Plex']['PLEX_URL'] = 'http://plex.example:32400'
    proxy._proxy_cache.clear()
    proxy.auth.set_token('secret-plex-token')
    monkeypatch.setattr(tmdb.themerr_db, 'find_movie_id_by_imdb', lambda *_: None)
    monkeypatch.setenv('TMDB_API_READ_ACCESS_TOKEN', 'tmdb-token')
    monkeypatch.setattr(proxy.requests, 'get', Mock(side_effect=requests.Timeout('timed out')))
    monkeypatch.setattr(tmdb.helpers, 'json_get', lambda **_: {'movie_results': [{'id': 10005}]})

    assert tmdb.get_tmdb_id_from_external_id('tt0497329', 'imdb', 'movie') == 10005
    assert proxy._proxy_cache == {}
