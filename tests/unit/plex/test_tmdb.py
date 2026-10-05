"""Plex TMDB proxy response validation and cache behavior."""

from unittest.mock import Mock

import pytest
import requests

from plex import tmdb


@pytest.mark.parametrize('data, cached', [({}, True), ([], False), (None, False), ('invalid', False)])
def test_only_valid_dictionary_responses_are_cached(configured, monkeypatch, data, cached):
    configured['Plex']['PLEX_URL'] = 'http://plex.example:32400'
    monkeypatch.setattr(tmdb, '_proxy_cache', {})
    monkeypatch.setattr(tmdb.auth, 'get_token', lambda: 'test-token')
    response = Mock()
    response.json.return_value = data
    request = Mock(return_value=response)
    monkeypatch.setattr(tmdb.requests, 'get', request)

    assert tmdb.query('find/tt123', {'external_source': 'imdb_id'}) == {}
    assert tmdb.query('find/tt123', {'external_source': 'imdb_id'}) == {}
    assert request.call_count == (1 if cached else 2)
    assert bool(tmdb._proxy_cache) == cached


@pytest.mark.parametrize('stage, error', [
    ('raise_for_status', requests.HTTPError('bad status')),
    ('json', ValueError('invalid JSON')),
])
def test_failed_responses_are_retried(configured, monkeypatch, stage, error):
    configured['Plex']['PLEX_URL'] = 'http://plex.example:32400'
    monkeypatch.setattr(tmdb, '_proxy_cache', {})
    monkeypatch.setattr(tmdb.auth, 'get_token', lambda: 'test-token')
    response = Mock()
    getattr(response, stage).side_effect = error
    request = Mock(return_value=response)
    monkeypatch.setattr(tmdb.requests, 'get', request)

    assert tmdb.query('find/tt123', {'external_source': 'imdb_id'}) == {}
    assert tmdb.query('find/tt123', {'external_source': 'imdb_id'}) == {}
    assert request.call_count == 2
    assert tmdb._proxy_cache == {}
