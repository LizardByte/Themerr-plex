"""Plex TMDb lookup behavior with deterministic responses."""

import pytest

from themerr import tmdb


def test_base_url(configured):
    configured['Plex']['PLEX_URL'] = 'https://plex.example'
    assert tmdb.tmdb_base_url() == 'https://plex.example/services/tmdb?uri='


@pytest.mark.parametrize('database,item_type,data,expected', [
    ('imdb', 'movie', {'movie_results': [{'id': '123'}]}, 123),
    ('tvdb', 'tv', {'tv_results': [{'id': 456}]}, 456),
    ('imdb', 'movie', {'movie_results': []}, None),
])
def test_external_lookup(configured, monkeypatch, database, item_type, data, expected):
    configured['Plex']['PLEX_URL'] = 'https://plex.example'
    calls = []
    monkeypatch.setattr(tmdb.helpers, 'json_get', lambda **kwargs: calls.append(kwargs) or data)
    assert tmdb.get_tmdb_id_from_external_id('tt 1', database, item_type) == expected
    assert 'tt+1' in calls[0]['url']


def test_external_invalid_and_error(configured, monkeypatch):
    assert tmdb.get_tmdb_id_from_external_id('x', 'invalid', 'movie') is None
    assert tmdb.get_tmdb_id_from_external_id('x', 'imdb', 'game') is None

    def fail(**_):
        raise RuntimeError('offline')

    monkeypatch.setattr(tmdb.helpers, 'json_get', fail)
    assert tmdb.get_tmdb_id_from_external_id('x', 'imdb', 'movie') is None


@pytest.mark.parametrize('name,expected', [
    ('James Bond', 645), ('James Bond Collection', 645), ('Unknown', None),
])
def test_collection_lookup(configured, monkeypatch, name, expected):
    configured['Plex']['PLEX_URL'] = 'https://plex.example'
    monkeypatch.setattr(tmdb.helpers, 'json_get', lambda **_: {
        'results': [{'name': 'James Bond Collection', 'id': '645'}],
    })
    assert tmdb.get_tmdb_id_from_collection(name) == expected
