"""Shared workers accept opaque IDs and do not depend on native SDK objects."""

# standard imports
from unittest.mock import Mock

# lib imports
import pytest

# local imports
from media_servers import processing
from media_servers.base import MediaServer, MediaServerBackend, MediaServerError
from themerr import storage


def test_interfaces_require_implementations():
    with pytest.raises(TypeError):
        MediaServer('server')
    with pytest.raises(TypeError):
        MediaServerBackend()


def test_workers_scope_opaque_ids_skip_inactive_servers_and_release_failed_work(monkeypatch):
    queue = processing._WorkQueue()
    monkeypatch.setattr(processing, 'q', queue)
    monkeypatch.setattr(processing, '_active_items', set())
    backend = Mock(spec=MediaServerBackend)
    backend.get_server.side_effect = lambda server_id: {'enabled': True} if server_id in ('a', 'b') else None
    adapter = Mock(spec=MediaServer)
    backend.server.return_value = adapter
    monkeypatch.setattr(processing, 'get_backend', lambda: backend)
    seen = []

    def update(item_id):
        server_id = storage.current_server_id()
        seen.append((server_id, item_id))
        assert not processing.enqueue(item_id)
        if server_id == 'a':
            raise OSError('Temporary upstream failure')

    adapter.update_item.side_effect = update
    for server_id in ('a', 'b', 'removed'):
        with storage.server_scope(server_id):
            assert processing.enqueue('opaque-item-uuid')
            assert not processing.enqueue('opaque-item-uuid')
    get = queue.get

    def next_work():
        if queue.empty():
            raise KeyboardInterrupt
        return get()

    monkeypatch.setattr(queue, 'get', next_work)
    with pytest.raises(KeyboardInterrupt):
        processing.process_queue()

    assert seen == [('a', 'opaque-item-uuid'), ('b', 'opaque-item-uuid')]
    assert queue.unfinished_tasks == 0
    assert not processing._active_items
    assert storage.current_server_id() == 'default'
    with storage.server_scope('a'):
        assert processing.enqueue('opaque-item-uuid')


def test_scan_uses_the_contract_and_keeps_other_servers_running(configured, monkeypatch):
    backend = Mock(spec=MediaServerBackend)
    backend.name = 'Plex'
    backend.list_servers.return_value = [{'id': 'a', 'name': 'A'}, {'id': 'b', 'name': 'B'}]
    first, second = Mock(spec=MediaServer), Mock(spec=MediaServer)
    first.scan.side_effect = OSError('Offline')
    backend.server.side_effect = [first, second]
    monkeypatch.setattr(processing, 'get_backend', lambda: backend)

    def scan(enqueue):
        assert storage.current_server_id() == 'b'
        assert enqueue is processing.enqueue

    second.scan.side_effect = scan
    processing.scheduled_update()

    backend.list_servers.assert_called_once_with(enabled_only=True)
    backend.record_refresh.assert_called_once_with(
        'a', 'Theme scan could not reach Plex. Check its address and access.')
    second.scan.assert_called_once()
    assert storage.current_server_id() == 'default'

    configured['Themerr']['BOOL_THEMERR_ENABLED'] = False
    backend.reset_mock()
    processing.scheduled_update()
    backend.list_servers.assert_not_called()


def test_scan_preserves_actionable_connector_error_and_continues(configured, monkeypatch):
    backend = Mock(spec=MediaServerBackend)
    backend.name = 'media server'
    backend.list_servers.return_value = [
        {
            'id': 'jellyfin:a',
            'name': 'A',
        },
        {
            'id': 'jellyfin:b',
            'name': 'B',
        },
    ]
    first, second = Mock(spec=MediaServer), Mock(spec=MediaServer)
    message = 'Install the matching Themerr connector and restart Jellyfin.'
    first.scan.side_effect = MediaServerError(message, 409)
    backend.server.side_effect = [first, second]
    log = Mock()
    monkeypatch.setattr(processing, 'get_backend', lambda: backend)
    monkeypatch.setattr(processing, 'log', log)
    processing.scheduled_update()
    backend.record_refresh.assert_called_once_with('jellyfin:a', message)
    second.scan.assert_called_once_with(processing.enqueue)
    log.warning.assert_called_once_with('Theme scan deferred for server %s: %s', 'jellyfin:a', message)
    log.exception.assert_not_called()
    assert storage.current_server_id() == 'default'
