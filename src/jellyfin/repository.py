"""Serve fixed connector artifacts over HTTP without exposing the administrator UI."""

from threading import Thread

from cryptography import x509
from fastapi import FastAPI
import uvicorn

from common import config, logger
from jellyfin import connector

log = logger.get_logger(__name__)
_server = None
_thread = None
_port = None


def create_app():
    """Expose only the code-owned public connector downloads and metadata."""
    from jellyfin.web import router
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.router.routes.extend(route for route in router.routes if route.path in connector.PUBLIC_PATHS)
    return app


def http_port():
    """Return the active repository port, excluding failed or disabled listeners."""
    return _port if _server is not None and _server.started else None


def start(cert_file):
    """Start a repository-only listener for a self-signed HTTPS installation."""
    global _server, _thread, _port
    port = config.CONFIG['Jellyfin']['REPOSITORY_HTTP_PORT']
    if not cert_file or not port or _server is not None:
        return
    with open(cert_file, 'rb') as stream:
        cert = x509.load_pem_x509_certificate(stream.read())
    try:
        cert.verify_directly_issued_by(cert)
    except (ValueError, TypeError):
        return
    if port == config.CONFIG['Network']['HTTP_PORT']:
        log.error('Connector HTTP port must differ from the administrator UI port.')
        return
    _port = port
    _server = uvicorn.Server(uvicorn.Config(
        create_app(), host=config.CONFIG['Network']['HTTP_HOST'], port=port,
        loop='asyncio', http='h11', ws='none', lifespan='off', proxy_headers=False,
        log_config=None, timeout_graceful_shutdown=5,
    ))
    server = _server

    def serve():
        try:
            server.run()
        except SystemExit:  # NOSONAR python:S5754: log Uvicorn's worker bind failure without an uncaught thread exit.
            log.error('Could not bind the connector HTTP listener. Check its configured port.')

    _thread = Thread(target=serve, name='Jellyfin connector repository', daemon=True)
    _thread.start()
    log.info('Connector downloads use HTTP port %s; the administrator UI stays on HTTPS.', port)


def stop():
    """Release the repository socket before a Themerr restart."""
    global _server, _thread, _port
    if _server is not None:
        _server.should_exit = True
    if _thread is not None:
        _thread.join(timeout=6)
    _server, _thread, _port = None, None, None
