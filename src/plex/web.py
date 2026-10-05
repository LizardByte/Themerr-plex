"""Plex sign-in and discovery routes protected by the shared browser middleware."""

import time

from fastapi import APIRouter, Depends, Request
from starlette.responses import JSONResponse, Response
from plexapi.exceptions import Unauthorized
from requests.exceptions import ConnectionError, RequestException, SSLError, Timeout
import requests

from common import logger, server_ui
from common.server_ui import _failure, _payload
from common.validation import ValidationError
from plex import auth as plex_auth
from plex import plexapi, servers, token_store

router = APIRouter()
log = logger.get_logger(__name__)
PLEX_LOGIN_LIFETIME = 600


@router.api_route('/api/plex/auth', methods=['GET', 'HEAD'], name='plex_auth_status', response_model=None)
def plex_auth_status() -> Response:
    """Report whether this installation has a token from Plex sign-in.

    The response contains only a connection flag and never includes the token.

    Returns
    -------
    Response
        Authentication status without exposing the token.

    Examples
    --------
    >>> plex_auth_status()
    <Response ...>
    """
    return JSONResponse({'connected': bool(plex_auth.get_token())})


@router.api_route('/api/plex/auth/start', methods=['POST'], name='plex_auth_start', response_model=None)
def plex_auth_start(request: Request) -> Response:
    """Start a Plex browser sign-in for this web session.

    Store the PIN in the browser session so it can be checked later.

    Parameters
    ----------
    request : Request
        Incoming browser or API request.

    Returns
    -------
    Response
        Plex authorization URL or a sanitized error.

    Examples
    --------
    >>> plex_auth_start(request)
    <Response ...>
    """
    try:
        login = plex_auth.start_login()
    except (OSError, KeyError, TypeError, ValueError):
        log.exception('Unable to start Plex sign-in')
        return JSONResponse({'message': 'Unable to start Plex sign-in. Please try again.'}, status_code=502)

    request.session['plex_login'] = {'pin_id': login['pin_id'], 'code': login['code'], 'started': time.time()}
    return JSONResponse({'auth_url': login['auth_url']})


@router.api_route('/api/plex/auth/check', methods=['POST'], name='plex_auth_check', response_model=None)
def plex_auth_check(request: Request) -> Response:
    """Finish a Plex sign-in once its PIN has been claimed.

    Keep the previous connection until the new token reaches the selected server.

    Parameters
    ----------
    request : Request
        Incoming browser or API request.

    Returns
    -------
    Response
        Pending, connected, expired, or error status.

    Examples
    --------
    >>> plex_auth_check(request)
    <Response ...>
    """
    login = request.session.get('plex_login')
    if not login:
        return JSONResponse({'message': 'Start Plex sign-in first.'}, status_code=400)
    if time.time() - login['started'] > PLEX_LOGIN_LIFETIME:
        request.session.pop('plex_login', None)
        return JSONResponse({'message': 'Plex sign-in expired. Please try again.'}, status_code=410)

    try:
        token = plex_auth.check_login(pin_id=login['pin_id'], code=login['code'])
    except requests.HTTPError as error:
        if error.response is not None and error.response.status_code in (404, 410):
            request.session.pop('plex_login', None)
            return JSONResponse({'message': 'Plex sign-in expired. Please try again.'}, status_code=410)
        log.warning('Unable to check Plex sign-in: %s', error)
        return JSONResponse({'message': 'Unable to check Plex sign-in. Please try again.'}, status_code=502)
    except (requests.RequestException, KeyError, TypeError, ValueError):
        log.exception('Unable to check Plex sign-in')
        return JSONResponse({'message': 'Unable to check Plex sign-in. Please try again.'}, status_code=502)

    if not token:
        return JSONResponse({'connected': False}, status_code=202)

    try:
        plex_auth.set_token(token)
    except OSError:
        log.exception('Unable to save Plex sign-in')
        return JSONResponse({'message': 'Unable to save Plex sign-in.'}, status_code=500)
    request.session.pop('plex_login', None)
    return JSONResponse({'connected': True})


@router.api_route('/api/plex/auth/disconnect', methods=['POST'], name='plex_auth_disconnect', response_model=None)
def plex_auth_disconnect(request: Request) -> Response:
    """Remove the local Plex connection.

    Clear the saved token and stop the active event listener.

    Parameters
    ----------
    request : Request
        Incoming browser or API request.

    Returns
    -------
    Response
        Disconnected status.

    Examples
    --------
    >>> plex_auth_disconnect(request)
    <Response ...>
    """
    try:
        servers.disconnect_account()
    except OSError:
        log.exception('Unable to disconnect Plex')
        return JSONResponse({'message': 'Unable to disconnect Plex.'}, status_code=500)

    plexapi.stop_plex_listener()
    servers.clear_connections()
    plexapi.plex_server = None
    request.session.pop('plex_login', None)
    return JSONResponse({'connected': False})


@router.api_route('/api/servers/discover', methods=['POST'], name='server_ui.discover', response_model=None)
def discover(payload=Depends(_payload)):
    """List account or LAN resources without disclosing access tokens.

    Returns
    -------
    Response
        Safe discovery results or a connection error.
    """
    source = payload.get('source')
    if source not in ('account', 'local'):
        return JSONResponse({'message': 'Choose account or local discovery.'}, status_code=400)
    try:
        resources = servers.discover_account() if source == 'account' else servers.discover_local()
        connected = {server['id'] for server in servers.list_servers()}
        resources = [{**resource, 'connected': resource['id'] in connected} for resource in resources]
    except Exception as exc:
        return _failure(exc, 'Discovery failed. Check the Plex connection, or enter an address manually.')
    return JSONResponse({'servers': resources})


@router.api_route('/api/servers', methods=['POST'], name='server_ui.add_server', response_model=None)
def add_server(payload=Depends(_payload)):
    """Connect to a selected or manually addressed server.

    Returns
    -------
    Response
        Saved public settings or a sanitized failure.
    """
    try:
        record = servers.add_server(payload.get('url', ''), payload.get('resource_id'))
    except token_store.TokenStorageError as exc:
        return _failure(exc, 'Unable to save the Plex token. Check the configured credential store.', 500)
    except SSLError as exc:
        return _failure(exc, 'The secure connection to Plex failed. Use its advertised HTTPS address and check '
                        'the server certificate.')
    except Timeout as exc:
        return _failure(exc, 'The Plex connection timed out. Check that the server is running and this address is '
                        'reachable from the machine running Themerr. Try another advertised or manual address.')
    except ConnectionError as exc:
        return _failure(exc, 'Could not connect to this Plex address. Check its hostname, port, and network access '
                        'from the machine running Themerr, or try another address.')
    except Unauthorized as exc:
        return _failure(exc, 'Plex denied access to this server. Check the linked account has permission, or '
                        'reconnect your Plex account.')
    except RequestException as exc:
        return _failure(exc, 'Plex returned an invalid response. Check the address or try another connection.')
    except ValidationError as exc:
        return _failure(exc, exc.reason.value, 400)
    except Exception as exc:
        return _failure(exc, 'Could not connect to this Plex server. Check the address and account access.')
    plexapi.plex_listener()
    server_ui._refresh()
    return JSONResponse({'server': record}, status_code=201)
