"""Refresh orchestration consumes only the backend contract."""

from unittest.mock import Mock

import pytest

from common import notifications
from media_servers.base import MediaServer, MediaServerBackend
from themerr import cache, storage


@pytest.mark.parametrize('outcome', [False, OSError('Offline'), True])
def test_failed_refresh_preserves_snapshot_and_suppresses_notification(configured, monkeypatch, outcome):
    snapshot = {'1': {'key': 1, 'title': 'Saved library', 'agent': 'saved', 'type': 'movie',
                      'media_count': 0, 'media_percent_complete': 0, 'collection_count': 0,
                      'collection_percent_complete': 0, 'collections_enabled': False,
                      'total_count': 0, 'items': []}}
    with storage.server_scope('a'):
        storage.replace_dashboard(snapshot)
    backend = Mock(spec=MediaServerBackend)
    backend.name = 'Plex'
    backend.list_servers.return_value = [{'id': 'a', 'name': 'A'}, {'id': 'b', 'name': 'B'}]
    first, second = Mock(spec=MediaServer), Mock(spec=MediaServer)
    if isinstance(outcome, Exception):
        first.cache_dashboard.side_effect = outcome
    else:
        first.cache_dashboard.return_value = outcome
    second.cache_dashboard.return_value = True
    backend.server.side_effect = [first, second]
    monkeypatch.setattr(cache, 'get_backend', lambda: backend)
    published = Mock()
    monkeypatch.setattr(notifications, 'refresh_completed', published)
    cache.cache_data()

    first.cache_dashboard.assert_called_once()
    second.cache_dashboard.assert_called_once()
    with storage.server_scope('a'):
        assert storage.get_dashboard() == snapshot
    assert storage.current_server_id() == 'default'
    if outcome is True:
        published.assert_called_once()
    else:
        published.assert_not_called()
    assert backend.record_refresh.call_args_list[-1].args == ('b',)


def test_empty_registry_does_not_connect_or_notify(configured, monkeypatch):
    backend = Mock(spec=MediaServerBackend)
    backend.list_servers.return_value = []
    monkeypatch.setattr(cache, 'get_backend', lambda: backend)
    published = Mock()
    monkeypatch.setattr(notifications, 'refresh_completed', published)
    cache.cache_data()
    backend.server.assert_not_called()
    published.assert_not_called()
