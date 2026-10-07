"""SSH cleanup verifies host identity, isolates credentials and confines remote deletion."""

# standard imports
import base64
from contextlib import contextmanager
import errno
import hashlib
import io
import json
import posixpath
import stat
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

# lib imports
from fastapi.testclient import TestClient
import paramiko
import pytest
from sqlalchemy.orm import Session

# local imports
from common import admin, credentials, webapp
from media_servers.base import MediaServerError
from plex import media, servers, ssh
from tests.http_helpers import set_session
from themerr import storage


class RemoteFiles:
    def __init__(self):
        self.entries = {
            '/plex': stat.S_IFDIR,
            '/plex/Metadata': stat.S_IFDIR,
        }
        self.redirects = {}
        self.removed = []
        self.shell_commands = []

    def directory(self, path):
        while path and path != '/':
            self.entries.setdefault(path, stat.S_IFDIR)
            path = posixpath.dirname(path)

    def file(self, path, data):
        self.directory(posixpath.dirname(path))
        self.entries[path] = data

    def normalize(self, path):
        for source, target in self.redirects.items():
            if path == source or path.startswith(f'{source}/'):
                return path.replace(source, target, 1)
        return path

    def lstat(self, path):
        if path not in self.entries:
            raise FileNotFoundError(errno.ENOENT, 'missing')
        value = self.entries[path]
        return SimpleNamespace(st_mode=stat.S_IFREG if isinstance(value, bytes) else value)

    def listdir_attr(self, path):
        return [
            SimpleNamespace(filename=posixpath.basename(name), st_mode=self.lstat(name).st_mode)
            for name in self.entries if posixpath.dirname(name) == path
        ]

    def open(self, path, mode):
        assert mode == 'rb'
        return io.BytesIO(self.entries[path])

    def remove(self, path):
        self.removed.append(path)
        del self.entries[path]

    def rmdir(self, path):
        assert not any(name.startswith(f'{path}/') for name in self.entries)
        self.removed.append(path)
        del self.entries[path]


@pytest.fixture
def remote(configured, monkeypatch):
    with Session(storage.engine()) as session:
        session.add(servers.ServerRecord(id='server', name='Plex', url='https://plex.example'))
        session.commit()
    files = RemoteFiles()
    connections = []

    @contextmanager
    def connect(public, secret):
        connections.append((
            public,
            secret,
        ))
        yield files

    monkeypatch.setattr(ssh, '_connection', connect)
    files.connections = connections
    return files


def values(**overrides):
    return {
        'host': 'plex.example',
        'port': 22,
        'username': 'plex-cleanup',
        'host_fingerprint': f'SHA256:{base64.b64encode(b"a" * 32).decode().rstrip("=")}',
        'data_directory': '/plex',
        'auth_type': 'password',
        'password': 'private-test-password',
        **overrides,
    }


def test_configuration_verifies_and_keeps_secrets_out_of_settings(remote):
    public = ssh.configure('server', values())
    assert 'password' not in public
    assert ssh.settings('server') == public
    assert remote.connections[0][1]['password'] == 'private-test-password'
    with Session(storage.engine()) as session:
        stored = session.get(storage.AppSetting, ssh._setting_id('server')).value
        assert 'private-test-password' not in stored
    ssh.configure('server', values(password=''))
    assert remote.connections[-1][1]['password'] == 'private-test-password'
    with pytest.raises(MediaServerError, match='Provide an SSH password'):
        ssh.configure('server', values(host='another.example', password=''))
    ssh.check('server')
    assert not remote.removed
    ssh.remove_settings('server')
    assert not ssh.settings('server')
    assert not credentials.get_token(ssh._credential_id('server'))


@pytest.mark.parametrize('field,value', [
    pytest.param('host', 'https://plex.example'),
    pytest.param('host', '../plex'),
    pytest.param('host', 'plex\n.example'),
    pytest.param('port', 0),
    pytest.param('port', True),
    pytest.param('port', '22'),
    pytest.param('host_fingerprint', 'unknown'),
    pytest.param('data_directory', '../plex'),
    pytest.param('data_directory', '/plex/../outside'),
    pytest.param('data_directory', 'C:Plex'),
    pytest.param('data_directory', '/plex/%2e%2e'),
    pytest.param('data_directory', r'C:\Plex\..\outside'),
    pytest.param('data_directory', r'C:\Plex\.\Metadata'),
    pytest.param('data_directory', r'C:\Plex\%2e%2e'),
    pytest.param('data_directory', r'C:\Plex\file:stream'),
    pytest.param('data_directory', r'C:\Plex\CON'),
    pytest.param('data_directory', r'C:\Plex\name.'),
    pytest.param('data_directory', r'\\host\share\Plex'),
    pytest.param('data_directory', r'\\?\C:\Plex'),
    pytest.param('data_directory', r'\\.\C:\Plex'),
    pytest.param('data_directory', r'\Plex'),
    pytest.param('data_directory', '//host/share/Plex'),
    pytest.param('data_directory', '/plex//Metadata'),
    pytest.param('data_directory', '/C:/Plex/../outside'),
    pytest.param('data_directory', 'C:\\Plex\nMetadata'),
    pytest.param('auth_type', 'agent'),
    pytest.param('password', None),
])
def test_rejects_invalid_settings_before_connecting(remote, field, value):
    with pytest.raises(MediaServerError):
        ssh.configure('server', values(**{field: value}))
    assert not remote.connections
    assert not ssh.settings('server')


def test_failed_verification_does_not_replace_configuration(remote):
    ssh.configure('server', values())
    previous = ssh.settings('server')
    with pytest.raises(OSError):
        ssh.configure('server', values(data_directory='/missing', password='replacement'))
    assert ssh.settings('server') == previous
    assert json.loads(credentials.get_token(ssh._credential_id('server')))['password'] == 'private-test-password'


def test_accepts_ipv6_host(remote):
    assert ssh.configure('server', values(host='::1'))['host'] == '::1'


@pytest.mark.parametrize('entered,canonical', [
    pytest.param(r'C:\Users\Plex\AppData\Local\Plex Media Server',
                 '/C:/Users/Plex/AppData/Local/Plex Media Server'),
    pytest.param('c:/Users/Plex/AppData/Local/Plex Media Server/',
                 '/C:/Users/Plex/AppData/Local/Plex Media Server'),
    pytest.param('/C:/Users/Plex/AppData/Local/Plex Media Server',
                 '/C:/Users/Plex/AppData/Local/Plex Media Server'),
    pytest.param('/plex/', '/plex'),
    pytest.param('C:\\', '/C:/'),
    pytest.param('/', '/'),
])
def test_directory_forms_are_verified_and_confine_cleanup(remote, item, entered, canonical):
    remote.entries[canonical] = stat.S_IFDIR
    remote.directory(posixpath.join(canonical, 'Metadata'))
    public = ssh.configure('server', values(data_directory=entered, username='plex'))
    assert remote.connections[0][0]['data_directory'] == canonical
    assert remote.connections[0][0]['username'] == 'plex'
    assert public['data_directory'] == canonical
    assert ssh.settings('server')['data_directory'] == canonical
    upload = posixpath.join(canonical, ssh._upload_directory(item, 'themes'))
    remote.file(f'{upload}/old', b'old audio')
    remote.file('/outside/precious', b'keep')
    ssh.remove_uploaded_media('server', item, 'themes')
    assert upload not in remote.entries
    assert remote.entries['/outside/precious'] == b'keep'


def test_each_server_uses_its_own_ssh_root_and_credentials(remote, item):
    with Session(storage.engine()) as session:
        session.add(servers.ServerRecord(id='second', name='Second Plex', url='https://second.example'))
        session.commit()
    remote.directory('/C:/Plex-Second/Metadata')
    ssh.configure('server', values(username='plex'))
    ssh.configure('second', values(
        username='plex-second',
        data_directory=r'C:\Plex-Second',
        password='second-test-password',
    ))
    relative = ssh._upload_directory(item, 'themes')
    first_upload = f'/plex/{relative}'
    second_upload = f'/C:/Plex-Second/{relative}'
    remote.file(f'{first_upload}/old', b'first theme')
    remote.file(f'{second_upload}/old', b'second theme')
    with storage.server_scope('server'):
        media.remove_uploaded_media(item, 'themes')
    assert first_upload not in remote.entries
    assert remote.entries[f'{second_upload}/old'] == b'second theme'
    assert remote.connections[-1][1]['password'] == 'private-test-password'
    with storage.server_scope('second'):
        media.remove_uploaded_media(item, 'themes')
    assert second_upload not in remote.entries
    assert remote.connections[-1][1]['password'] == 'second-test-password'
    ssh.remove_settings('server')
    assert ssh.settings('second')['data_directory'] == '/C:/Plex-Second'
    assert credentials.get_token(ssh._credential_id('second'))


def test_pins_server_host_key():
    key = SimpleNamespace(asbytes=lambda: b'actual-host-key')
    fingerprint = f'SHA256:{base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("=")}'
    ssh._PinnedHostKey(fingerprint).missing_host_key(None, 'host', key)
    with pytest.raises(paramiko.SSHException, match='fingerprint mismatch'):
        ssh._PinnedHostKey(values()['host_fingerprint']).missing_host_key(None, 'host', key)


def test_connection_uses_only_selected_credentials(configured, monkeypatch):
    client = MagicMock()
    client.__enter__.return_value = client
    sftp = MagicMock()
    sftp.__enter__.return_value = sftp
    client.open_sftp.return_value = sftp
    monkeypatch.setattr(ssh.paramiko, 'SSHClient', lambda: client)
    public = ssh._validate(values())
    with ssh._connection(public, {'password': 'private-test-password'}):
        pass
    options = client.connect.call_args.kwargs
    assert options['allow_agent'] is False
    assert options['look_for_keys'] is False
    assert options['password'] == 'private-test-password'
    assert isinstance(client.set_missing_host_key_policy.call_args.args[0], ssh._PinnedHostKey)
    client.exec_command.assert_not_called()
    client.invoke_shell.assert_not_called()
    client.connect.side_effect = paramiko.AuthenticationException('private-server-detail')
    with pytest.raises(MediaServerError, match='Unable to connect') as error:
        with ssh._connection(public, {'password': 'private-test-password'}):
            pass
    assert 'private-server-detail' not in str(error.value)


def test_private_key_and_passphrase_parsing():
    key = paramiko.RSAKey.generate(2048)
    output = io.StringIO()
    key.write_private_key(output, password='key-passphrase')
    assert ssh._private_key({
        'private_key': output.getvalue(),
        'passphrase': 'key-passphrase',
    }) == key
    with pytest.raises(MediaServerError, match='private key'):
        ssh._private_key({
            'private_key': output.getvalue(),
            'passphrase': 'incorrect',
        })


def test_cleanup_retains_verified_theme_and_isolated_other_item(remote, item):
    ssh.configure('server', values())
    upload = f'/plex/{ssh._upload_directory(item, "themes")}'
    remote.file(f'{upload}/new', b'verified audio')
    remote.file(f'{upload}/nested/old', b'old audio')
    remote.file('/plex/Metadata/other-item/Uploads/themes/old', b'other item')
    digest = hashlib.sha256(b'verified audio').hexdigest()
    ssh.remove_uploaded_media('server', item, 'themes', digest)
    assert remote.entries[f'{upload}/new'] == b'verified audio'
    assert remote.entries['/plex/Metadata/other-item/Uploads/themes/old'] == b'other item'
    assert remote.removed == [f'{upload}/nested/old']
    ssh.remove_uploaded_media('server', item, 'themes')
    assert upload not in remote.entries
    ssh.remove_uploaded_media('server', item, 'themes')


def test_missing_verified_upload_prevents_any_deletion(remote, item):
    ssh.configure('server', values())
    upload = f'/plex/{ssh._upload_directory(item, "themes")}'
    remote.file(f'{upload}/old', b'old audio')
    with pytest.raises(MediaServerError, match='Existing uploads were kept'):
        ssh.remove_uploaded_media('server', item, 'themes', 'a' * 64)
    assert not remote.removed


@pytest.mark.parametrize('link_type', [
    'symlink',
    'junction',
    'ancestor',
])
def test_links_escaping_to_similarly_named_sibling_are_rejected(remote, item, link_type):
    ssh.configure('server', values())
    relative = ssh._upload_directory(item, 'themes')
    upload = f'/plex/{relative}'
    remote.file(f'{upload}/old', b'old')
    remote.file('/plex-other/precious', b'keep')
    link = f'{upload}/link'
    remote.entries[link] = stat.S_IFLNK if link_type == 'symlink' else stat.S_IFDIR
    remote.redirects[link if link_type != 'ancestor' else '/plex/Metadata'] = '/plex-other'
    with pytest.raises(MediaServerError, match='unsafe'):
        ssh.remove_uploaded_media('server', item, 'themes')
    assert remote.entries['/plex-other/precious'] == b'keep'
    assert not remote.removed


@pytest.mark.parametrize('name', [
    '../outside',
    '%2e%2e',
    'C:\\outside',
    '\\\\host\\share',
    'file:stream',
    'CON',
    'name\x00',
])
def test_remote_filenames_are_validated_before_any_removal(remote, item, name, monkeypatch):
    ssh.configure('server', values())
    upload = f'/plex/{ssh._upload_directory(item, "themes")}'
    remote.file(f'{upload}/old', b'old')
    monkeypatch.setattr(remote, 'listdir_attr', lambda _: [SimpleNamespace(filename=name, st_mode=stat.S_IFREG)])
    with pytest.raises(MediaServerError, match='unsafe'):
        ssh.remove_uploaded_media('server', item, 'themes')
    assert not remote.removed


def test_media_prefers_ssh_and_propagates_failure(remote, item, monkeypatch):
    ssh.configure('server', values())
    remove = Mock(side_effect=MediaServerError('SSH unavailable', 502))
    monkeypatch.setattr(ssh, 'remove_uploaded_media', remove)
    local = Mock()
    monkeypatch.setattr(media, 'get_media_upload_path', local)
    with storage.server_scope('server'), pytest.raises(MediaServerError, match='SSH unavailable'):
        media.remove_uploaded_media(item, 'themes')
    remove.assert_called_once_with('server', item, 'themes', None)
    local.assert_not_called()


def test_ssh_routes_authentication_csrf_and_secret_redaction(remote, monkeypatch):
    monkeypatch.setattr(admin, 'HASH_METHOD', 'scrypt:16384:8:1')
    current = admin._save('admin', 'a unique test password')
    with TestClient(webapp.create_app(https_only=False), base_url='https://localhost',
                    follow_redirects=False) as client:
        url = '/api/plex/servers/server/ssh'
        assert client.put(url, json=values()).status_code == 401
        set_session(client, {'admin_revision': current['revision']})
        assert client.put(url, json=values()).status_code == 400
        client.app.state.csrf_enabled = False
        result = client.put(url, json=values())
        assert result.status_code == 200
        assert 'private-test-password' not in result.text
        assert 'private-test-password' not in client.get(url).text
        assert 'private-test-password' not in client.get('/servers').text
        assert 'SSH cleanup' in client.get('/servers').text
        assert client.post(f'{url}/check').status_code == 200
        assert client.delete(url).status_code == 200
        assert not ssh.settings('server')
        assert client.get('/api/plex/servers/unknown/ssh').status_code == 404
    assert not remote.removed


def test_remote_http_cannot_submit_ssh_credentials(remote, monkeypatch):
    monkeypatch.setattr(admin, 'HASH_METHOD', 'scrypt:16384:8:1')
    current = admin._save('admin', 'a unique test password')
    app = webapp.create_app(https_only=False)
    with TestClient(app, base_url='http://themerr.example', client=(
        '192.0.2.5',
        50000,
    )) as client:
        set_session(client, {'admin_revision': current['revision']})
        app.state.csrf_enabled = False
        result = client.put('/api/plex/servers/server/ssh', json=values())
        assert result.status_code == 409
        assert 'Use HTTPS' in result.json()['message']
    assert not remote.connections
    assert not ssh.settings('server')


def test_removing_server_erases_ssh_settings_and_credentials(remote):
    ssh.configure('server', values())
    servers.remove_server('server')
    assert not servers.get_server('server')
    assert not ssh.settings('server')
    assert not credentials.get_token(ssh._credential_id('server'))
    assert not remote.removed
