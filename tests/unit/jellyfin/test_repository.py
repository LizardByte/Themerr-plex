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


@pytest.mark.parametrize('self_signed, port, mcp_http, expected', [
    pytest.param(True, 9495, False, True),
    pytest.param(False, 9495, False, False),
    pytest.param(True, 0, False, False),
    pytest.param(True, 9494, False, False),
    pytest.param(True, 9495, True, True),
    pytest.param(False, 9495, True, True),
    pytest.param(False, 0, True, False),
    pytest.param(True, 9494, True, False),
])
def test_http_listener_respects_tls_mcp_enablement_and_port(
        configured, monkeypatch, tmp_path, self_signed, port, mcp_http, expected):
    configured['Jellyfin']['REPOSITORY_HTTP_PORT'] = port
    configured['Network']['MCP_HTTP'] = mcp_http
    certificate = Mock()
    if not self_signed:
        certificate.verify_directly_issued_by.side_effect = ValueError('Not self-signed')
    monkeypatch.setattr(repository.x509, 'load_pem_x509_certificate', Mock(return_value=certificate))
    server = Mock(started=True)

    def make_server(configuration):
        server.config = configuration
        return server

    factory = Mock(side_effect=make_server)
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
    assert repository.mcp_http_port() == (port if expected and mcp_http else None)
    if expected:
        assert factory.call_args.args[0].ssl_certfile is None
        assert factory.call_args.args[0].lifespan == 'on'
        configured['Network']['MCP_HTTP'] = not mcp_http
        assert repository.mcp_http_port() == (port if mcp_http else None)
        thread.call_args.kwargs['target']()
        server.run.assert_called_once_with()
        server.started = False
        server.run.side_effect = SystemExit(1)
        thread.call_args.kwargs['target']()
        assert repository.http_port() is None
        assert repository.mcp_http_port() is None
        repository.stop()
        assert server.should_exit is True
        worker.join.assert_called_once_with(timeout=6)
        assert repository.http_port() is None
