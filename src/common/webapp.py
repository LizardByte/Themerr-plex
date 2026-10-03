"""
src/common/webapp.py

Responsible for serving the webapp.
"""
# standard imports
import copy
import os
import secrets
import time
from threading import Event

# lib imports
from fastapi import APIRouter, Depends, FastAPI, Request
from starlette.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from starlette.requests import ClientDisconnect
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
import uvicorn
import anyio
from plexapi import exceptions as plex_exceptions
import requests
from werkzeug.utils import secure_filename

# local imports
import common
from common import admin, api_docs, server_ui
from common.http import csrf_token as _csrf_token
from common.http import error_response, file_response, read_form, read_json, render_template
from common import config
from common import crypto
from common.definitions import Paths
from common import locales
from common import logger
from plex import auth as plex_auth
from themerr import storage

# variables
URL_SCHEME = None
URL = None
MIMETYPE_TEXT_PLAIN = 'text/plain'

# localization
_ = locales.get_text()

# mime type map
mime_type_map = {
    'gif': 'image/gif',
    'ico': 'image/vnd.microsoft.icon',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'png': 'image/png',
    'svg': 'image/svg+xml',
}

router = APIRouter()
log = logger.get_logger(__name__)
PLEX_LOGIN_LIFETIME = 600


@router.api_route('/home', methods=['GET', 'HEAD'], name='home', response_model=None)
@router.api_route('/', methods=['GET', 'HEAD'], name='home', response_model=None)
def home(request: Request) -> Response:
    """
    Serve the webapp home page.

    Show cached Plex library data once it is available. Until then, show a progress page.

    Parameters
    ----------
    request : Request
        Incoming browser or API request.

    Returns
    -------
    render_template
        The dashboard, or a cache progress page before dashboard data exists.

    Notes
    -----
    A cache read failure produces the HTTP 500 response. The following routes trigger this function.

        `/`
        `/home`

    Examples
    --------
    >>> home(request)
    """
    try:
        items, errors, stats = server_ui.dashboard()
    except Exception:
        log.exception('Unable to load dashboard')
        return render_template(
            request,
            'error.html',
            title='Unable to load libraries',
            message='The dashboard could not be loaded. Try again or check the log.',
            status_code=500,
        )
    return render_template(
        request,
        'home.html',
        title='Overview',
        items=items,
        theme_errors=errors,
        stats=stats,
        servers=server_ui.servers.list_servers(),
    )


async def _stream_theme_audio(upstream: requests.Response, rating_key: int):
    """Stream Plex audio and release the connection when playback stops.

    Parameters
    ----------
    upstream : requests.Response
        Open streaming response from the configured Plex server.
    rating_key : int
        Plex item identifier for diagnostic logging.

    Yields
    ------
    bytes
        Audio chunks without buffering the entire theme in memory.
    """
    chunks = upstream.iter_content(chunk_size=64 * 1024)
    try:
        while True:
            chunk = await anyio.to_thread.run_sync(next, chunks, None, abandon_on_cancel=True)
            if chunk is None:
                break
            yield chunk
    except requests.RequestException as error:
        log.warning('Theme playback interrupted for rating_key=%s (%s)', rating_key, type(error).__name__)


class ThemeAudioResponse(StreamingResponse):
    """Stream theme audio with guaranteed upstream cleanup.

    Close the Plex connection even when sending headers or chunks is cancelled.

    Parameters
    ----------
    upstream : requests.Response
        Open audio response from Plex.
    rating_key : int
        Item identifier used for playback diagnostics.
    headers : dict
        Validated media headers for the browser response.

    Examples
    --------
    >>> response = ThemeAudioResponse(upstream, 42, {'Content-Type': 'audio/mpeg'})
    """

    def __init__(self, upstream: requests.Response, rating_key: int, headers: dict):
        """Stream the open upstream response without buffering its audio."""
        self.upstream = upstream
        super().__init__(_stream_theme_audio(upstream, rating_key), status_code=upstream.status_code,
                         headers=headers)

    async def __call__(self, scope, receive, send):
        """Send the streaming response and release its upstream connection.

        Close the connection outside the event loop, including on ASGI disconnects.

        Parameters
        ----------
        scope : dict
            ASGI request scope.
        receive : callable
            ASGI receive function.
        send : callable
            ASGI send function.

        Examples
        --------
        >>> await response(scope, receive, send)
        """
        try:
            await super().__call__(scope, receive, send)
        except ClientDisconnect:
            pass
        finally:
            with anyio.CancelScope(shield=True):
                await run_in_threadpool(self.upstream.close)


@router.api_route(
    '/api/themes/{rating_key:int}',
    methods=['GET', 'HEAD'],
    name='play_theme_default',
    response_model=None,
)
@router.api_route(
    '/api/servers/{server_id}/themes/{rating_key:int}',
    methods=['GET', 'HEAD'],
    name='play_theme',
    response_model=None,
)
def play_theme(request: Request, rating_key: int, server_id: str = 'default') -> Response:
    """Serve the item's current Plex theme without exposing the Plex token.

    Resolve the selected audio from fresh Plex metadata and forward byte range requests
    so browsers can determine the duration. Only media response headers reach the browser.

    Parameters
    ----------
    request : Request
        Incoming browser or API request.
    rating_key : int
        Item whose selected theme should be played, regardless of its provider.
    server_id : str
        Plex machine identifier.

    Returns
    -------
    Response
        Streamed audio, including byte range headers, or a sanitized error.

    Examples
    --------
    >>> play_theme(request, rating_key=42)  # FastAPI invokes this for GET /api/themes/42
    <Response ...>
    """
    from plex import plexapi

    try:
        with storage.server_scope(server_id):
            server = plexapi.setup_plexapi()
        if server is None:
            return JSONResponse({'message': 'Connect to Plex before playing themes.'}, status_code=503)
        item = server.fetchItem(rating_key)
        theme_path = getattr(item, 'theme', None)
        if not theme_path:
            return JSONResponse({'message': 'This item has no theme.'}, status_code=404)
        if not theme_path.startswith('/library/metadata/') or '/theme/' not in theme_path:
            return JSONResponse({'message': 'Plex returned an unsupported theme path.'}, status_code=502)

        headers = {'Accept-Encoding': 'identity'}
        for header in ('Range', 'If-Range'):
            value = request.headers.get(header)
            if value is not None:
                headers[header] = value
        upstream = server._session.get(
            server.url(theme_path, includeToken=False), headers=server._headers(**headers),
            stream=True, allow_redirects=False, timeout=config.CONFIG['Themerr']['INT_PLEXAPI_PLEXAPI_TIMEOUT'],
        )
    except plex_exceptions.NotFound:
        return JSONResponse({'message': 'This Plex item is no longer available.'}, status_code=404)
    except (plex_exceptions.PlexApiException, OSError, ValueError) as error:
        log.warning('Unable to load theme for rating_key=%s (%s)', rating_key, type(error).__name__)
        return JSONResponse({'message': 'Unable to load theme audio from Plex.'}, status_code=502)

    return _theme_audio_response(request, upstream, rating_key)


def _theme_audio_response(request: Request, upstream: requests.Response, rating_key: int) -> Response:
    """Build a browser response and close rejected Plex audio streams.

    Parameters
    ----------
    request : Request
        Incoming browser or API request.
    upstream : requests.Response
        Stream returned by Plex.
    rating_key : int
        Plex item identifier for playback diagnostics.

    Returns
    -------
    Response
        Validated audio stream, or a sanitized playback error.
    """
    headers = {'Cache-Control': 'no-store'}
    for header in ('Content-Type', 'Content-Length', 'Content-Range', 'Accept-Ranges', 'ETag', 'Last-Modified'):
        if header in upstream.headers:
            headers[header] = upstream.headers[header]
    if upstream.status_code not in (200, 206):
        upstream.close()
        if upstream.status_code == 416:
            headers['Content-Length'] = '0'
            return Response(status_code=416, headers=headers)
        status = 404 if upstream.status_code == 404 else 502
        log.warning('Plex rejected theme playback for rating_key=%s (HTTP %s)', rating_key, upstream.status_code)
        return JSONResponse({'message': 'Plex could not provide theme audio.'}, status_code=status)
    content_type = upstream.headers.get('Content-Type', 'application/octet-stream').split(';', 1)[0].lower()
    if not content_type.startswith('audio/') and content_type not in ('video/mp4', 'application/octet-stream'):
        upstream.close()
        return JSONResponse({'message': 'Plex returned an unsupported audio format.'}, status_code=502)
    headers['Content-Type'] = content_type
    if request.method == 'HEAD':
        upstream.close()
        return Response(status_code=upstream.status_code, headers=headers)

    return ThemeAudioResponse(upstream, rating_key, headers)


@router.api_route('/settings/', methods=['GET', 'HEAD'], name='settings', response_model=None)
def settings(request: Request) -> Response:
    """
    Serve the configuration page.

    Decode any masked settings for display and render the current configuration specification.

    Parameters
    ----------
    request : Request
        Incoming browser or API request.

    Returns
    -------
    render_template
        The settings form populated with decoded values and the application specification.

    Notes
    -----
    The following routes trigger this function.

        `/settings`

    Examples
    --------
    >>> settings(request)
    """
    config_settings = config.decode_config(common.CONFIG)
    return render_template(
        request,
        'config.html',
        title=_('Settings'),
        config_settings=config_settings,
        config_spec=config._CONFIG_SPEC_DICT,
    )


@router.api_route('/api/directories', methods=['POST'], name='browse_directories', response_model=None)
def browse_directories(payload=Depends(read_json)) -> Response:
    """List server directories for the configuration folder picker.

    The response contains directory names and paths, without file contents. The request is
    protected by the same CSRF check as other settings actions.

    Parameters
    ----------
    payload : object or None
        Decoded JSON body, supplied by the request dependency.

    Returns
    -------
    Response
        Current directory, parent directory, and child directories.

    Examples
    --------
    >>> browse_directories()  # FastAPI invokes this for POST /api/directories
    """
    requested = payload.get('path', '') if isinstance(payload, dict) else None
    if not isinstance(requested, str) or len(requested) > 4096 or '\x00' in requested:
        return JSONResponse({'message': 'Invalid directory path.'}, status_code=400)
    requested = requested or os.path.expanduser('~')
    if not os.path.isabs(requested):
        return JSONResponse({'message': 'Directory path must be absolute.'}, status_code=400)

    try:
        directory = os.path.realpath(requested)
        with os.scandir(directory) as entries:
            children = sorted(
                ({'name': entry.name, 'path': os.path.realpath(entry.path)}
                 for entry in entries if entry.is_dir()),
                key=lambda entry: entry['name'].casefold(),
            )
    except OSError:
        return JSONResponse({'message': 'Directory is unavailable.'}, status_code=400)

    parent = os.path.dirname(directory)
    return JSONResponse({'path': directory, 'parent': parent if parent != directory else None, 'directories': children})


@router.api_route('/docs/', methods=['GET', 'HEAD'], name='docs', response_model=None)
@router.api_route('/docs/{filename:path}', methods=['GET', 'HEAD'], name='docs_file', response_model=None)
def docs(filename: str = 'index.html') -> Response:
    """
    Serve the Sphinx html documentation.

    Resolve the requested page from the built documentation directory.

    Parameters
    ----------
    filename : str
        Path to an HTML documentation file relative to the built documentation directory.

    Returns
    -------
    FileResponse
        The requested documentation page, or a 404 response when the file is absent.

    Notes
    -----
    The following routes trigger this function.

        `/docs/`
        `/docs/<page.html>`

    Examples
    --------
    >>> docs(filename='index.html')
    """

    return file_response(Paths.DOCS_DIR, filename or 'index.html')


@router.api_route('/favicon.ico', methods=['GET', 'HEAD'], name='favicon', response_model=None)
@router.api_route('/images/{img:path}', methods=['GET', 'HEAD'], name='image', response_model=None)
def image(img: str = 'favicon.ico') -> Response:
    """
    Get image from static/images directory.

    Serve images from the static/images directory.

    Parameters
    ----------
    img : str
        The image to return.

    Returns
    -------
    FileResponse
        The image.

    Notes
    -----
    The following routes trigger this function.

        - `/favicon.ico`
        - `/images/<img>`

    Examples
    --------
    >>> image('favicon.ico')
    """
    directory = os.path.join(Paths.ROOT_DIR, 'web', 'images')
    filename = os.path.basename(secure_filename(filename=img))  # sanitize the input

    if os.path.isfile(os.path.join(directory, filename)):
        file_extension = filename.rsplit('.', 1)[-1]
        if file_extension in mime_type_map:
            return file_response(directory, filename, mime_type_map[file_extension])
        else:
            return Response(content='Invalid file type', status_code=400, media_type=MIMETYPE_TEXT_PLAIN)
    else:
        return Response(content='Image not found', status_code=404, media_type=MIMETYPE_TEXT_PLAIN)


@router.api_route('/status', methods=['GET', 'HEAD'], name='status', response_model=None)
def status() -> dict:
    """
    Check the status of Themerr-plex.

    This is useful for a healthcheck from Docker, and may have many other uses in the future for third party
    applications.

    Returns
    -------
    dict
        A dictionary of the status.

    Examples
    --------
    >>> status()
    """
    web_status = {'result': 'success', 'message': 'Ok'}
    return web_status


@router.api_route('/test_logger', methods=['POST'], name='test_logger', response_model=None)
def test_logger() -> Response:
    """
    Test logging functions.

    Check `./logs/common.webapp.log` for output.

    Returns
    -------
    Response
        A message telling the user to check the logs.

    Notes
    -----
    The following routes trigger this function.

        `/test_logger`

    Examples
    --------
    >>> test_logger()
    """
    message = 'testing from log'
    log.info(message)
    log.warning(message)
    log.error(message)
    log.critical(message)
    log.debug(message)
    return PlainTextResponse(f'Testing complete, check "logs/{__name__}.log" for output.')


def _parse_setting(option: str, value: str) -> tuple[str, str, object]:
    """Validate and convert one submitted setting.

    Parameters
    ----------
    option : str
        Section and setting name separated by a pipe.
    value : str
        Submitted form value.

    Returns
    -------
    tuple[str, str, object]
        Section, setting name, and converted value.

    Raises
    ------
    KeyError
        The setting is unknown or locked.
    ValueError
        The value cannot be converted.
    """
    key, separator, setting = option.partition('|')
    spec = config._CONFIG_SPEC_DICT.get(key, {}).get(setting)
    if not separator or not isinstance(spec, dict) or spec.get('locked'):
        raise KeyError(option)

    try:
        if spec['type'] == 'boolean':
            value = {'true': True, 'false': False}[value.lower()]
        elif spec['type'] == 'float':
            value = float(value)
        elif spec['type'] == 'integer':
            value = int(value)
    except (KeyError, ValueError) as exc:
        raise ValueError(option) from exc
    return key, setting, value


def _candidate_settings(form) -> tuple[dict, list[tuple[str, str]], Response | None]:
    """Build a validated candidate from the submitted settings form.

    Returns
    -------
    tuple[dict, list[tuple[str, str]], Response or None]
        Candidate configuration, changed keys, and an error response if parsing failed.
    """
    candidate = copy.deepcopy(config.CONFIG)
    decoded = config.decode_config(common.CONFIG)
    changed = []
    for option, value in form.items():
        try:
            key, setting, value = _parse_setting(option, value)
        except KeyError:
            error = JSONResponse({'status': 'ERROR', 'message': 'Unknown or locked setting.'}, status_code=400)
            return candidate, changed, error
        except ValueError:
            error = JSONResponse({'status': 'ERROR', 'message': 'Invalid setting value.'}, status_code=400)
            return candidate, changed, error

        if decoded[key][setting] != value:
            changed.append((key, setting))
        if config.is_masked_field(section=key, key=setting):
            value = config.encode_value(value)
        candidate[key][setting] = value
    return candidate, changed, None


def _save_settings(candidate: dict, changed: list[tuple[str, str]]) -> Response:
    """Save changed settings and restore previous values on failure.

    Parameters
    ----------
    candidate : dict
        Validated candidate configuration.
    changed : list[tuple[str, str]]
        Section and setting names that changed.

    Returns
    -------
    Response
        Save result for the web client.
    """
    originals = {(key, setting): config.CONFIG[key][setting] for key, setting in changed}
    for key, setting in changed:
        config.CONFIG[key][setting] = candidate[key][setting]
    if not config.save_config(config=config.CONFIG):
        for (key, setting), value in originals.items():
            config.CONFIG[key][setting] = value
        return JSONResponse({'status': 'ERROR', 'message': 'Unable to save settings.'}, status_code=500)
    for key, setting in changed:
        on_change = config._CONFIG_SPEC_DICT[key][setting].get('on_change')
        if on_change:
            on_change()
    if any(key == 'Themerr' and setting in (
            'BOOL_THEMERR_ENABLED', 'INT_UPDATE_THEMES_INTERVAL', 'INT_UPDATE_DATABASE_CACHE_INTERVAL',
    ) for key, setting in changed):
        from themerr import scheduled_tasks
        scheduled_tasks.configure_jobs()
    return JSONResponse({'status': 'OK', 'message': 'Selected settings are valid.'})


@router.api_route('/api/settings', methods=['GET', 'POST', 'HEAD'], name='api_settings', response_model=None)
def api_settings(request: Request, form=Depends(read_form)) -> Response:
    """
    Get current settings or save changes to settings from the web ui.

    This endpoint accepts a `GET` or `POST` request. A `GET` request will return the current settings.
    A `POST` request will process the data passed in and return the results of processing.

    Parameters
    ----------
    request : Request
        Incoming browser or API request.
    form : FormData
        Submitted settings fields, parsed before the endpoint runs.

    Returns
    -------
    Response
        A response formatted as ``JSONResponse``.

    Examples
    --------
    >>> api_settings(request)
    <Response ... bytes [200 OK]>
    """
    if request.method in ('GET', 'HEAD'):
        return JSONResponse(config.CONFIG)

    candidate, changed, error = _candidate_settings(form)
    if error is not None:
        return error
    if not config.validate_config(config=candidate):
        return JSONResponse({'status': 'ERROR', 'message': 'Selected settings are not valid.'}, status_code=400)
    return _save_settings(candidate, changed)


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
        server_ui.servers.disconnect_account()
    except OSError:
        log.exception('Unable to disconnect Plex')
        return JSONResponse({'message': 'Unable to disconnect Plex.'}, status_code=500)

    from plex import plexapi
    plexapi.stop_plex_listener()
    server_ui.servers.clear_connections()
    plexapi.plex_server = None
    request.session.pop('plex_login', None)
    return JSONResponse({'connected': False})


@router.api_route('/translations', methods=['GET', 'HEAD'], name='translations', response_model=None)
def translations() -> Response:
    """
    Serve the translations.

    Gets the user's locale and serves the translations for the webapp.

    Returns
    -------
    Response
        The translations.

    Examples
    --------
    >>> translations()
    """
    language = locales.get_translation()
    data = {}
    while language is not None:
        for message, translation in getattr(language, '_catalog', {}).items():
            if isinstance(message, str) and message and translation:
                data.setdefault(message, translation)
        language = language._fallback
    return JSONResponse(data)


@router.get('/api/docs', name='api_documentation', include_in_schema=False, response_model=None)
def api_documentation(request: Request) -> Response:
    """Serve authenticated interactive API documentation with bundled Swagger assets.

    Use the same session, origin policy, and CSRF checks as the browser interface.

    Parameters
    ----------
    request : Request
        Signed-in browser request.

    Returns
    -------
    Response
        API documentation using this browser's session and CSRF token.

    Examples
    --------
    >>> response = api_documentation(request)
    """
    return render_template(request, 'api_docs.html', title='API documentation')


@router.get('/api/openapi.json', include_in_schema=False)
def api_schema(request: Request) -> dict:
    """Serve the authenticated OpenAPI schema.

    Fill CSRF header defaults for this browser without modifying the cached schema.

    Parameters
    ----------
    request : Request
        Signed-in browser request.

    Returns
    -------
    dict
        API operations, request bodies, and authentication requirements.

    Examples
    --------
    >>> document = api_schema(request)
    """
    document = copy.deepcopy(request.app.openapi())
    token = _csrf_token(request)
    for methods in document['paths'].values():
        for operation in methods.values():
            for parameter in operation.get('parameters', []):
                if parameter['name'] == 'X-CSRFToken':
                    parameter['schema'] = {**parameter['schema'], 'default': token}
    return document


async def browser_error(request: Request, error: HTTPException) -> Response:
    """Handle HTTP failures from browser and API routes.

    Render errors in a worker thread while retaining the exception's response headers.

    Parameters
    ----------
    request : Request
        Failed request.
    error : HTTPException
        HTTP status, public detail, and optional headers.

    Returns
    -------
    Response
        JSON or HTML error response.

    Examples
    --------
    >>> response = await browser_error(request, HTTPException(404, 'Not Found'))
    """
    return await run_in_threadpool(error_response, request, error.status_code, str(error.detail), error.headers)


async def unexpected_error(request: Request, error: Exception) -> Response:
    """Handle unexpected failures with a generic error response.

    Log the exception and retain browser security headers without exposing internal details.

    Parameters
    ----------
    request : Request
        Failed request.
    error : Exception
        Unexpected exception recorded in the application log.

    Returns
    -------
    Response
        Generic HTTP 500 response.

    Examples
    --------
    >>> response = await unexpected_error(request, RuntimeError('unavailable'))
    """
    log.error('Unexpected web request failure', exc_info=error)
    response = await run_in_threadpool(error_response, request, 500, 'Internal Server Error')
    admin._security_headers(request, response.headers)
    return response


def create_app(*, https_only: bool | None = None) -> FastAPI:
    """Build an ASGI application with private routes and signed browser sessions.

    Retain the browser interface, bounded requests, and bundled documentation routes.

    Parameters
    ----------
    https_only : bool or None
        Secure-cookie policy, defaulting to the configured TLS setting.

    Returns
    -------
    FastAPI
        Application serving the existing HTML pages and JSON API.

    Examples
    --------
    >>> application = create_app(https_only=True)
    """
    application = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    application.state.secret_key = secrets.token_hex(32)
    application.state.csrf_enabled = True
    application.state.static_directory = os.path.join(Paths.ROOT_DIR, 'web', 'assets')
    if https_only is None:
        https_only = bool(config.CONFIG and config.CONFIG['Network']['SSL'])
    application.add_middleware(admin.BrowserSecurityMiddleware)
    application.add_middleware(SessionMiddleware, secret_key=application.state.secret_key,
                               max_age=12 * 60 * 60, same_site='lax', https_only=https_only)
    application.include_router(admin.router)
    application.include_router(server_ui.router)
    application.include_router(router)

    def openapi():
        if application.openapi_schema is None:
            routes = [*admin.router.routes, *server_ui.router.routes, *router.routes]
            application.openapi_schema = api_docs.schema(routes)
        return application.openapi_schema

    application.openapi = openapi
    application.mount('/web/assets', StaticFiles(directory=application.state.static_directory, check_dir=False),
                      name='static')
    application.add_exception_handler(HTTPException, browser_error)
    application.add_exception_handler(Exception, unexpected_error)
    logging_filter = admin._SetupLinkFilter()
    access_logger = logger.get_logger('uvicorn.access')
    if not any(isinstance(value, admin._SetupLinkFilter) for value in access_logger.filters):
        access_logger.addFilter(logging_filter)
    return application


app = create_app()
_server = None
_server_stopped = Event()
_server_stopped.set()


def start_webapp() -> None:
    """Serve FastAPI in the application's web thread.

    Use the configured host, port, and optional TLS certificate with Uvicorn.

    Examples
    --------
    >>> start_webapp()
    """
    global URL, URL_SCHEME, _server, app
    URL_SCHEME = 'https' if config.CONFIG['Network']['SSL'] else 'http'
    URL = f"{URL_SCHEME}://127.0.0.1:{config.CONFIG['Network']['HTTP_PORT']}"
    cert_file, key_file = crypto.initialize_certificate() if config.CONFIG['Network']['SSL'] else (None, None)
    app = create_app()
    server_config = uvicorn.Config(
        app, host=config.CONFIG['Network']['HTTP_HOST'], port=config.CONFIG['Network']['HTTP_PORT'],
        loop='asyncio', http='h11', ws='none', lifespan='off', proxy_headers=False, log_config=None,
        ssl_certfile=cert_file, ssl_keyfile=key_file, timeout_graceful_shutdown=5,
    )
    _server = uvicorn.Server(server_config)
    _server_stopped.clear()
    try:
        _server.run()
    finally:
        _server = None
        _server_stopped.set()


def stop_webapp() -> None:
    """Stop the active Uvicorn server.

    Release the listening socket before shutdown or a replacement process starts.

    Examples
    --------
    >>> stop_webapp()
    """
    if _server is not None:
        _server.should_exit = True
        _server_stopped.wait(timeout=6)
