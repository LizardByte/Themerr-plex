"""Authenticated Jellyfin setup and exact public routes for bundled plugin artifacts."""

from fastapi import APIRouter, Depends, Request
from starlette.responses import JSONResponse

from common import credentials, logger
from common.http import file_response, read_json
from jellyfin import connector, servers
from media_servers.base import MediaServerError

router = APIRouter()
log = logger.get_logger(__name__)
_ARCHIVE_PATHS = {'/jellyfin/connector/' + name: name for name in connector.ARCHIVES.values()}


def _failure(exc):
    """Expose fixed adapter messages and log only the failure category."""
    if isinstance(exc, MediaServerError):
        return JSONResponse({'message': str(exc)}, status_code=exc.status_code)
    log.warning('Jellyfin setup failed (%s)', type(exc).__name__)
    message = ('Could not access the secure credential store.' if isinstance(exc, credentials.TokenStorageError)
               else 'Could not complete Jellyfin setup. Check the server connection and logs.')
    return JSONResponse({'message': message}, status_code=502)


def _payload(value):
    """Reject arrays and scalars without echoing submitted credentials."""
    if not isinstance(value, dict):
        raise MediaServerError('Invalid JSON object.', 400)
    return value


@router.post('/api/jellyfin/servers', name='jellyfin.add_server', response_model=None)
def add_server(payload=Depends(read_json)):
    """Verify and securely save a Jellyfin server using an administrator API key."""
    try:
        payload = _payload(payload)
        result = servers.add_server(payload.get('url'), payload.get('api_key'))
        return JSONResponse({'message': 'Jellyfin server connected.', 'server': result}, status_code=201)
    except Exception as exc:
        return _failure(exc)


@router.get('/api/jellyfin/servers/{server_id}/connector', name='jellyfin.connector_status', response_model=None)
def connector_status(server_id: str):
    """Check the installed connector without changing Jellyfin or its repositories."""
    try:
        connection = servers.client(server_id)
        connector.verify(connection)
        return JSONResponse({'installed': True, 'message': 'Matching connector is active.'})
    except Exception as exc:
        return _failure(exc)


@router.post('/api/jellyfin/servers/{server_id}/connector', name='jellyfin.install_connector', response_model=None)
def install_connector(server_id: str, payload=Depends(read_json)):
    """Register the local repository and install the exact matching connector; restart is manual."""
    try:
        payload = _payload(payload)
        result = connector.install(servers.client(server_id), payload.get('themerr_url'))
        return JSONResponse(result, status_code=202)
    except Exception as exc:
        return _failure(exc)


@router.api_route(connector.MANIFEST_PATH, methods=['GET', 'HEAD'], name='jellyfin.manifest', response_model=None)
def manifest():
    """Serve only bundled connector metadata so Jellyfin can install from this Themerr instance."""
    try:
        return JSONResponse(connector.manifest())
    except MediaServerError as exc:
        return _failure(exc)


@router.api_route('/jellyfin/connector/connector-10.11.zip', methods=['GET', 'HEAD'],
                  name='jellyfin.archive_10_11', response_model=None)
@router.api_route('/jellyfin/connector/connector-12.1.zip', methods=['GET', 'HEAD'],
                  name='jellyfin.archive_12_1', response_model=None)
def archive(request: Request):
    """Serve fixed build-owned plugin filenames through the shared file policy."""
    try:
        connector.bundle()
        return file_response(str(connector.directory()), _ARCHIVE_PATHS[request.url.path], 'application/zip')
    except MediaServerError as exc:
        return _failure(exc)
