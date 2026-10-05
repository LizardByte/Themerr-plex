"""The self-signed certificate fallback exposes only fixed connector downloads."""

from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from jellyfin import connector, repository


def test_http_repository_exposes_no_admin_or_setup_routes(configured, connector_bundle):
    connector.repository_url('http://themerr.example:9495')
    with TestClient(repository.create_app()) as client:
        assert client.get(connector.MANIFEST_PATH).status_code == 200
        image = client.get(connector.THUMBNAIL_PATH)
        assert image.status_code == 200
        assert image.headers['Content-Type'] == 'image/png'
        assert image.content == (connector.directory() / 'thumb.png').read_bytes()
        assert client.head(connector.THUMBNAIL_PATH).content == b''
        for filename in connector.ARCHIVES.values():
            assert client.get('/jellyfin/connector/' + filename).status_code == 200
            assert client.head('/jellyfin/connector/' + filename).content == b''
        for path in ('/login', '/setup', '/status', '/api/settings', '/api/jellyfin/servers',
                     '/openapi.json', '/docs', '/jellyfin/connector/bundle.json',
                     '/jellyfin/connector/%2e%2e%2fconfig.ini', '/jellyfin/connector/CON',
                     '/jellyfin/connector/C:%5cconfig.ini', '/jellyfin/connector/connector-12.1.zip:secret'):
            assert client.get(path).status_code == 404
        assert client.post(connector.MANIFEST_PATH).status_code == 405
        assert client.post(connector.THUMBNAIL_PATH).status_code == 405


@pytest.mark.parametrize('self_signed, port, expected', [
    (True, 9495, True), (False, 9495, False), (True, 0, False), (True, 9494, False)])
def test_listener_runs_only_for_self_signed_tls_on_a_separate_enabled_port(
        configured, monkeypatch, tmp_path, self_signed, port, expected):
    configured['Jellyfin']['REPOSITORY_HTTP_PORT'] = port
    certificate = Mock()
    if not self_signed:
        certificate.verify_directly_issued_by.side_effect = ValueError('Not self-signed')
    monkeypatch.setattr(repository.x509, 'load_pem_x509_certificate', Mock(return_value=certificate))
    server = Mock(started=True)
    factory = Mock(return_value=server)
    monkeypatch.setattr(repository.uvicorn, 'Server', factory)
    worker = Mock()
    thread = Mock(return_value=worker)
    monkeypatch.setattr(repository, 'Thread', thread)
    monkeypatch.setattr(repository, '_server', None)
    monkeypatch.setattr(repository, '_thread', None)
    monkeypatch.setattr(repository, '_port', None)
    path = tmp_path / 'certificate.pem'
    path.write_bytes(b'certificate')
    repository.start(str(path))
    assert factory.called is expected
    assert repository.http_port() == (port if expected else None)
    if expected:
        assert factory.call_args.args[0].ssl_certfile is None
        thread.call_args.kwargs['target']()
        server.run.assert_called_once_with()
        repository.stop()
        assert server.should_exit is True
        worker.join.assert_called_once_with(timeout=6)
        assert repository.http_port() is None
