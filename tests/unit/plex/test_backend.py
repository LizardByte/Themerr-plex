"""Plex adapters retain identity and translate only at native boundaries."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from media_servers import get_backend
from media_servers.base import MediaServerBackend
from plex import dashboard, plexapi, tmdb
from plex.backend import PlexBackend, PlexMediaServer
from themerr import storage


def test_selection_contains_only_the_plex_implementation():
    assert isinstance(get_backend(), MediaServerBackend)
    assert isinstance(get_backend(), PlexBackend)
    assert get_backend() is get_backend()


def test_adapter_scopes_library_cache_scan_update_and_metadata_operations(monkeypatch):
    adapter = PlexMediaServer('saved')
    seen = []

    def scoped(result):
        seen.append(storage.current_server_id())
        return result

    section = SimpleNamespace(key=1, title='Movies')
    connection = SimpleNamespace(library=SimpleNamespace(sections=lambda: scoped([section])))
    monkeypatch.setattr(plexapi, 'setup_plexapi', lambda: connection)
    monkeypatch.setattr(dashboard, '_cache_server', lambda: scoped(True))
    monkeypatch.setattr(plexapi, 'scan_items', lambda enqueue: enqueue('42'))
    monkeypatch.setattr(tmdb, 'query', lambda path, params: scoped({'id': 7}))
    update = Mock(side_effect=lambda rating_key: scoped(True))
    monkeypatch.setattr(plexapi, 'update_plex_item', update)
    with storage.server_scope('parent'):
        assert adapter.libraries() == [{'id': '1', 'title': 'Movies'}]
        assert adapter.cache_dashboard()
        assert adapter.update_item('42')
        assert adapter.query_tmdb('find/tt42', {}) == {'id': 7}
        adapter.scan(lambda item_id: scoped(item_id == '42'))
        assert storage.current_server_id() == 'parent'
    update.assert_called_once_with(rating_key=42)
    assert seen == ['saved'] * 5

    update.side_effect = OSError('Offline')
    with pytest.raises(OSError):
        adapter.update_item('42')
    assert storage.current_server_id() == 'default'


def test_plex_browser_urls_encode_identifiers():
    urls = PlexMediaServer('server /?').web_urls('library &', 'item ?')
    assert urls['server'] == 'https://app.plex.tv/desktop/#!/media/server%20%2F%3F/com.plexapp.plugins.library'
    assert urls['library'].endswith('?source=library+%26')
    assert urls['item'].endswith('/details?key=%2Flibrary%2Fmetadata%2Fitem+%3F')
