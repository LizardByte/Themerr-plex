"""Browser authentication and fixed public Jellyfin repository resources."""

import re
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from common import admin, webapp
from jellyfin import connector, maintenance, servers
from media_servers.base import MediaServerError
from tests.http_helpers import set_session


@pytest.fixture
def browser(configured):
    with TestClient(webapp.create_app(https_only=False), follow_redirects=False) as client:
        yield client


def sign_in(browser):
    current = admin._save('admin', 'a long unique passphrase')
    set_session(browser, {'admin_revision': current['revision']})
    token = re.search(rb'name="csrf-token" content="([^"]+)"', browser.get('/servers').content).group(1).decode()
    return {'X-CSRFToken': token}


def test_repository_is_public_but_setup_and_sibling_paths_are_private(browser, connector_bundle, monkeypatch):
    connector.repository_url('http://themerr.example:9494')
    assert browser.get(connector.MANIFEST_PATH).status_code == 200
    for name in connector.ARCHIVES.values():
        result = browser.get('/jellyfin/connector/' + name)
        assert result.status_code == 200
        assert result.headers['Content-Type'] == 'application/zip'
        assert browser.head('/jellyfin/connector/' + name).content == b''
    add = Mock()
    monkeypatch.setattr(servers, 'add_server', add)
    assert browser.post('/api/jellyfin/servers', json={'api_key': 'secret'}).status_code == 401
    assert browser.get('/jellyfin/connector/bundle.json').status_code == 302
    headers = sign_in(browser)
    assert browser.post('/api/jellyfin/servers', json={}).status_code == 400
    assert browser.get('/jellyfin/connector/bundle.json').status_code == 404
    assert browser.post('/jellyfin/connector/connector-12.1.zip', headers=headers).status_code == 405
    add.assert_not_called()


@pytest.mark.parametrize('path', [
    '../config.ini', '%2e%2e%2fconfig.ini', 'C:%5cconfig.ini',
    '..%5cconfig.ini', 'connector-12.1.zip:secret', 'CON',
])
def test_repository_rejects_unmapped_paths(browser, connector_bundle, path):
    sign_in(browser)
    assert browser.get('/jellyfin/connector/' + path).status_code == 404


def test_archive_symlink_escape_is_rejected(browser, connector_bundle, tmp_path):
    directory = connector.directory()
    target = tmp_path / 'connector-sibling'
    target.mkdir()
    (target / 'outside.zip').write_bytes(b'private')
    archive = directory / 'connector-12.1.zip'
    archive.unlink()
    try:
        archive.symlink_to(target / 'outside.zip')
    except OSError:
        pytest.skip('Creating symlinks requires privileges on this host.')
    assert browser.get('/jellyfin/connector/connector-12.1.zip').status_code == 404


def test_api_key_is_not_echoed_in_setup_response(browser, monkeypatch):
    headers = sign_in(browser)
    add = Mock(return_value={'id': 'jellyfin:' + '3' * 32, 'name': 'Jellyfin', 'enabled': True})
    monkeypatch.setattr(servers, 'add_server', add)
    result = browser.post('/api/jellyfin/servers', json={'url': 'http://jellyfin.example', 'api_key': 'secret'},
                          headers=headers)
    assert result.status_code == 201
    assert b'secret' not in result.content
    add.assert_called_once_with('http://jellyfin.example', 'secret')


@pytest.mark.parametrize('online', [True, False])
def test_connector_status_retains_restart_notices_while_offline_or_already_matching(
        browser, connector_bundle, monkeypatch, online):
    sign_in(browser)
    server_id = 'jellyfin:' + '3' * 32
    monkeypatch.setattr(servers, 'get_server', lambda _: {'id': server_id})
    client = Mock()
    if not online:
        client.side_effect = MediaServerError('Unavailable', 502)
    monkeypatch.setattr(servers, 'client', client)
    monkeypatch.setattr(connector, 'verify', Mock(return_value=connector_bundle))
    maintenance._save(server_id, phase='restarting', message='Restarting Jellyfin.', restart_required=True)
    result = browser.get('/api/jellyfin/servers/' + server_id + '/connector')
    assert result.status_code == 200
    assert result.json()['message'] == 'Restarting Jellyfin.'
    assert result.json()['restart_required'] is True
    assert result.json()['installed'] is online
