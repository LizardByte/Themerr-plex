"""Public file routes must contain every filesystem lookup within their own root."""

# standard imports
import os

# lib imports
from fastapi.testclient import TestClient
import pytest

# local imports
from common import admin, webapp
from common.definitions import Paths
from tests.http_helpers import set_session

PUBLIC = b'0123456789'
PRIVATE = b'private file contents must never be served'
ROUTES = ('/docs', '/images', '/web/assets')


@pytest.fixture
def public_files(configured, monkeypatch, tmp_path):
    root = tmp_path / 'installation'
    directories = {
        '/docs': root / 'docs',
        '/images': root / 'web' / 'images',
        '/web/assets': root / 'web' / 'assets',
    }
    for directory in directories.values():
        directory.mkdir(parents=True)
        (directory / 'public.png').write_bytes(PUBLIC)
        (directory / 'nested').mkdir()
        (directory / 'nested' / 'public.png').write_bytes(PUBLIC)
        (directory.parent / 'private.png').write_bytes(PRIVATE)
        sibling = directory.with_name(directory.name + '-private')
        sibling.mkdir()
        (sibling / 'private.png').write_bytes(PRIVATE)
    (directories['/docs'] / 'index.html').write_bytes(PUBLIC)
    monkeypatch.setattr(Paths, 'ROOT_DIR', str(root))
    monkeypatch.setattr(Paths, 'DOCS_DIR', str(directories['/docs']))
    monkeypatch.setattr(admin, 'HASH_METHOD', 'scrypt:16384:8:1')
    account = admin._save('admin', 'a unique test password')
    with TestClient(webapp.create_app(https_only=False), base_url='http://localhost') as client:
        set_session(client, {'admin_revision': account['revision']})
        yield client, directories


@pytest.mark.parametrize('route', ROUTES)
@pytest.mark.parametrize('filename', [
    '%2e%2e/private.png',
    '%2e%2e%2fprivate.png',
    'nested/%2e%2e/%2e%2e/private.png',
    '%252e%252e%252fprivate.png',
    '%2e%2e%5cprivate.png',
    '%2e%2e%20/private.png',
    '%2e%2e%2e/private.png',
    '%2e/public.png',
    'nested/%2e%2e/public.png',
    '%2fprivate.png',
    'C%3a%2fWindows%2fwin.ini',
    'C%3a..%5cprivate.png',
    '%5c%5cserver%5cshare%5cprivate.png',
    '%5c%5c%3f%5cC%3a%5cprivate.png',
    'public.png%3asecret',
    'NUL', 'CON.png', 'aux.txt',
    'public.png%00', 'public.png%09', 'public.png%7f',
    'public.png%20', 'public.png.',
])
def test_public_routes_reject_ambiguous_and_traversing_paths(public_files, route, filename):
    client, _ = public_files
    for method in (client.get, client.head):
        response = method(route + '/' + filename)
        assert response.status_code == 404
        assert PRIVATE not in response.content


@pytest.mark.parametrize('route', ROUTES)
def test_public_routes_preserve_nested_files_head_and_byte_ranges(public_files, route):
    client, _ = public_files
    for filename in ('public.png', 'nested/public.png'):
        url = route + '/' + filename
        response = client.get(url)
        assert response.status_code == 200
        assert response.content == PUBLIC
        assert response.headers['content-length'] == str(len(PUBLIC))
        assert response.headers['content-type'] == 'image/png'
        head = client.head(url)
        assert head.status_code == 200
        assert head.content == b''
        assert head.headers['content-length'] == str(len(PUBLIC))
        partial = client.get(url, headers={'Range': 'bytes=2-4'})
        assert partial.status_code == 206
        assert partial.content == PUBLIC[2:5]
        assert partial.headers['content-range'] == 'bytes 2-4/10'
        invalid = client.get(url, headers={'Range': 'bytes=100-'})
        assert invalid.status_code == 416
    assert client.get('/docs/').content == PUBLIC


def _directory_link(target, link):
    """Exercise actual Windows junctions or POSIX symlinks without elevated privileges."""
    if os.name == 'nt':
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


@pytest.mark.parametrize('route', ROUTES)
def test_public_routes_reject_links_to_same_prefix_sibling_directories(public_files, route):
    client, directories = public_files
    directory = directories[route]
    sibling = directory.with_name(directory.name + '-private')
    _directory_link(sibling, directory / 'escape')
    for method in (client.get, client.head):
        response = method(route + '/escape/private.png')
        assert response.status_code == 404
        assert PRIVATE not in response.content


@pytest.mark.parametrize('route', ROUTES)
def test_public_routes_allow_links_only_when_the_target_remains_inside(public_files, route):
    client, directories = public_files
    directory = directories[route]
    _directory_link(directory / 'nested', directory / 'inside')
    response = client.get(route + '/inside/public.png')
    assert response.status_code == 200
    assert response.content == PUBLIC
