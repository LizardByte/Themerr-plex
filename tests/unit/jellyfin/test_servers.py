"""Connection validation and credential isolation across Plex and Jellyfin."""

from pathlib import Path
from unittest.mock import Mock

from cryptography.fernet import Fernet
import pytest
import requests

from common import credentials
from jellyfin import servers
from jellyfin.client import Client, base_url, identifier
from media_servers.base import MediaServerError
from themerr import storage


def response(data, status=200):
    return Mock(status_code=status, json=Mock(return_value=data))


def test_saved_key_never_appears_in_public_settings(configured, monkeypatch):
    monkeypatch.setattr(requests, 'request', lambda *_args, **_kwargs: response(
        {'Id': '3' * 32, 'ServerName': 'Jellyfin', 'Version': '12.1.0'}))
    result = servers.add_server('http://jellyfin.example:8096/prefix', 'a-private-jellyfin-key')
    assert result['id'] == 'jellyfin:' + '3' * 32
    assert 'a-private-jellyfin-key' not in str(result)
    assert credentials.get_token(servers.credential_id(result['id'])) == 'a-private-jellyfin-key'
    servers.update_server(result['id'], {'enabled': False, 'ignored_libraries': '4' * 32})
    with pytest.raises(MediaServerError, match='paused'):
        servers.client(result['id'])
    servers.remove_server(result['id'])
    assert servers.list_servers() == []
    assert credentials.get_token(servers.credential_id(result['id'])) == ''


def test_headless_plex_and_jellyfin_keys_use_independent_encrypted_slots(configured, tmp_path, monkeypatch):
    key = tmp_path / 'secret.key'
    key.write_bytes(Fernet.generate_key())
    monkeypatch.setenv(credentials.KEY_FILE_ENV, str(key))
    credentials.save_token('plex-account', 'private-plex-key')
    credentials.save_token('server:installation:plex-server', 'private-plex-server-key')
    credentials.save_token('jellyfin:installation:jellyfin-server', 'private-jellyfin-key')
    assert credentials.get_token('plex-account') == 'private-plex-key'
    assert credentials.get_token('server:installation:plex-server') == 'private-plex-server-key'
    assert credentials.get_token('jellyfin:installation:jellyfin-server') == 'private-jellyfin-key'
    assert b'private-jellyfin-key' not in Path(storage.database_path()).read_bytes()
    credentials.delete_token('jellyfin:installation:jellyfin-server')
    assert credentials.get_token('plex-account') == 'private-plex-key'


@pytest.mark.parametrize('url', [
    None, 'file:///etc/passwd', 'http://u:p@host', 'http://host?token=secret',
    'http://host/%2fpath', 'http://host/../other', 'http://host\\other',
    'http://host:99999', 'http://host\n/',
])
def test_invalid_addresses_are_rejected(url):
    with pytest.raises(MediaServerError):
        base_url(url)


@pytest.mark.parametrize('item_id', ['../file', 'C:\\file', '%2fetc', 'bad', None])
def test_item_identifiers_cannot_supply_paths(item_id):
    with pytest.raises(MediaServerError):
        identifier(item_id)


def test_client_keeps_credentials_in_headers_and_rejects_redirects(monkeypatch):
    request = Mock(return_value=response({}, 302))
    monkeypatch.setattr(requests, 'request', request)
    with pytest.raises(MediaServerError):
        Client('http://jellyfin.example', 'secret').request('GET', '/System/Info')
    assert request.call_args.kwargs['headers'] == {'Authorization': 'MediaBrowser Token="secret"'}
    assert request.call_args.kwargs['allow_redirects'] is False
    request.return_value.close.assert_called_once()


def test_changed_server_address_is_rejected(configured, monkeypatch):
    info = {'Id': '3' * 32, 'ServerName': 'Jellyfin', 'Version': '12.1.0'}
    request = Mock(return_value=response(info))
    monkeypatch.setattr(requests, 'request', request)
    saved = servers.add_server('http://jellyfin.example', 'private-key')
    request.return_value = response({**info, 'Id': '4' * 32})
    with pytest.raises(MediaServerError, match='different Jellyfin server'):
        servers.client(saved['id'])


def test_client_pins_json_profile_for_both_jellyfin_versions(monkeypatch):
    result = response({'Version': '12.1.0'})
    request = Mock(return_value=result)
    monkeypatch.setattr(requests, 'request', request)
    connection = Client('http://jellyfin.example', 'secret')
    assert connection.json('GET', '/System/Info') == {'Version': '12.1.0'}
    assert connection.server_version == '12.1.0'
    assert request.call_args.kwargs['headers']['Accept'] == 'application/json; profile="PascalCase"'
    result.close.assert_called_once()
