"""Request parsing, translated templates, and browser tokens for the ASGI web UI."""

# standard imports
from functools import lru_cache
import hashlib
import hmac
import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit

# lib imports
from fastapi import HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from starlette.datastructures import FormData
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.templating import Jinja2Templates

# local imports
from common import locales
from common.definitions import Paths

templates = Jinja2Templates(directory=os.path.join(Paths.ROOT_DIR, 'web', 'templates'))
templates.env.trim_blocks = True
templates.env.lstrip_blocks = True
templates.env.globals.update(int=int, str=str)
templates.env.add_extension('jinja2.ext.i18n')
CSRF_LIFETIME = 3600


@lru_cache(maxsize=8)
def _asset_version(path: str, modified: int, size: int) -> str:
    """Cache a content fingerprint until a browser asset changes on disk."""
    with open(path, 'rb') as asset:
        return hashlib.file_digest(asset, 'sha256').hexdigest()[:16]


def asset_url(request: Request, filename: str) -> str:
    """Return the asset path with a cached content fingerprint.

    Parameters
    ----------
    request : Request
        Request carrying the application's asset directory.
    filename : str
        Compiled asset name.

    Returns
    -------
    str
        Relative asset URL, versioned when the file exists.
    """
    path = os.path.join(request.app.state.static_directory, filename)
    url = str(request.app.url_path_for('static', path=filename))
    try:
        stat = os.stat(path)
        return f'{url}?v={_asset_version(path, stat.st_mtime_ns, stat.st_size)}'
    except OSError:
        return url


def csrf_token(request: Request) -> str:
    """Sign a time-limited token bound to this browser's session."""
    value = request.session.setdefault('csrf_token', secrets.token_hex(32))
    return URLSafeTimedSerializer(request.app.state.secret_key, salt='csrf-token').dumps(value)


async def validate_csrf(request: Request) -> None:
    """Validate unsafe requests, including the same-origin HTTPS referer."""
    if request.method in ('GET', 'HEAD', 'OPTIONS', 'TRACE') or not request.app.state.csrf_enabled:
        return
    token = request.headers.get('X-CSRFToken') or request.headers.get('X-CSRF-Token')
    if not token:
        token = (await read_form(request)).get('csrf_token')
    if not isinstance(token, str):
        raise HTTPException(400, 'The CSRF token is missing.')
    try:
        value = URLSafeTimedSerializer(request.app.state.secret_key, salt='csrf-token').loads(
            token, max_age=CSRF_LIFETIME,
        )
    except BadSignature:
        raise HTTPException(400, 'The CSRF token is invalid or expired.') from None
    expected = request.session.get('csrf_token')
    if not isinstance(value, str) or not isinstance(expected, str) or not hmac.compare_digest(value, expected):
        raise HTTPException(400, 'The CSRF token does not match this session.')
    if request.url.scheme == 'https':
        try:
            origin = urlsplit(request.headers.get('referer', ''))
            same_origin = (origin.scheme == 'https' and origin.hostname == request.url.hostname and
                           (origin.port or 443) == (request.url.port or 443))
        except ValueError:
            same_origin = False
        if not same_origin:
            raise HTTPException(400, 'A same-origin referer is required.')


async def read_form(request: Request) -> FormData:
    """Parse a bounded browser form.

    Read the body asynchronously before a synchronous endpoint enters a worker thread.

    Parameters
    ----------
    request : Request
        Incoming browser request.

    Returns
    -------
    FormData
        Submitted fields, with file uploads disabled.

    Examples
    --------
    >>> form = await read_form(request)
    """
    return await request.form(max_files=0, max_fields=256, max_part_size=64 * 1024)


async def read_json(request: Request):
    """Read JSON from the incoming request.

    Accept JSON media types and return None for absent or malformed JSON bodies.

    Parameters
    ----------
    request : Request
        Incoming API request.

    Returns
    -------
    object or None
        Decoded JSON value, or None when no valid JSON body is available.

    Examples
    --------
    >>> payload = await read_json(request)
    """
    media_type = request.headers.get('content-type', '').split(';', 1)[0].strip().lower()
    if media_type != 'application/json' and not (
        media_type.startswith('application/') and media_type.endswith('+json')
    ):
        return None
    try:
        return await request.json()
    except (ValueError, UnicodeDecodeError):
        return None


def render_template(request: Request, template_name: str, *, status_code: int = 200,
                    headers=None, **context) -> Response:
    """Render a translated browser page.

    Supply request-local translations, signed CSRF tokens, and relative route URLs.

    Parameters
    ----------
    request : Request
        Request carrying the browser session and route context.
    template_name : str
        Name of the Jinja template under web/templates.
    status_code : int, optional
        HTTP response status.
    headers : dict or None, optional
        Additional response headers.
    **context : dict
        Page-specific template values.

    Returns
    -------
    Response
        Rendered HTML page.

    Examples
    --------
    >>> response = render_template(request, 'error.html', title='404', message='Not Found')
    """
    locale_id = locales.get_locale()
    language = locales.get_translation(locale_id)
    title = context.get('title')
    if title:
        context['title'] = language.gettext(title)
    context = {
        'locale_id': locale_id.replace('_', '-'),
        'admin_username': getattr(request.state, 'admin_username', None),
        'current_endpoint': getattr(request.scope.get('route'), 'name', None),
        'url_for': lambda name, **values: str(request.app.url_path_for(name, **values)),
        'asset_url': lambda filename: asset_url(request, filename),
        'csrf_token': lambda: csrf_token(request),
        '_': language.gettext,
        'gettext': language.gettext,
        'ngettext': language.ngettext,
        **context,
    }
    return templates.TemplateResponse(request=request, name=template_name, context=context,
                                      status_code=status_code, headers=headers)


def file_response(directory: str, filename: str, media_type: str | None = None) -> FileResponse:
    """Serve a file inside the requested directory.

    Resolve the path before serving it, rejecting missing files and directory traversal.

    Parameters
    ----------
    directory : str
        Root directory containing public files.
    filename : str
        Relative filename within that directory.
    media_type : str or None, optional
        Explicit media type, or None to infer it from the filename.

    Returns
    -------
    FileResponse
        File response supporting conditional and byte-range requests.

    Raises
    ------
    HTTPException
        The file is missing or resolves outside the directory.

    Examples
    --------
    >>> response = file_response(Paths.DOCS_DIR, 'index.html')
    """
    root = Path(directory).resolve()
    path = (root / filename).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, 'Not Found')
    return FileResponse(path, media_type=media_type)


def error_response(request: Request, status_code: int, message: str, headers=None) -> Response:
    """Format an error for its browser or API client.

    Return JSON for API routes and the existing HTML error template for browser pages.

    Parameters
    ----------
    request : Request
        Request whose path determines the response format.
    status_code : int
        HTTP error status.
    message : str
        Public error description.
    headers : dict or None, optional
        Additional response headers.

    Returns
    -------
    Response
        JSON or HTML error response.

    Examples
    --------
    >>> response = error_response(request, 404, 'Not Found')
    """
    if request.url.path.startswith('/api/'):
        return JSONResponse({'message': message}, status_code=status_code, headers=headers)
    return render_template(request, 'error.html', status_code=status_code, headers=headers,
                           title=str(status_code), message=message)
