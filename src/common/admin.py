"""Single-administrator authentication and browser security boundaries."""

# standard imports
from collections import OrderedDict
import hmac
import json
import logging
import secrets
from threading import RLock
import time
from urllib.parse import urlsplit

# lib imports
from fastapi import APIRouter, Depends, Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash

# local imports
from common.http import error_response, read_form, render_template, validate_csrf
from common.helpers import get_logger
from common.validation import ValidationError, ValidationMessage
from themerr import storage

router = APIRouter()
LOGIN_ENDPOINT = 'admin.login'
SETUP_ENDPOINT = 'admin.setup'
AUTH_TEMPLATE = 'auth.html'
HASH_METHOD = 'scrypt:131072:8:1'
SETUP_TOKEN = secrets.token_urlsafe(32)
_lock = RLock()
_attempts = OrderedDict()
LOGIN_WINDOW = 900


class _SetupLinkFilter(logging.Filter):
    """Keep the one-time setup secret out of HTTP access logs."""

    def filter(self, record):
        """Redact the setup token before an access record is formatted.

        Parameters
        ----------
        record : LogRecord
            HTTP access record.

        Returns
        -------
        bool
            Always allow the sanitized record.
        """
        record.msg = record.getMessage().replace(SETUP_TOKEN, '[redacted]')
        record.args = ()
        return True


def account() -> dict | None:
    """Read the application's sole administrator.

    Returns
    -------
    dict or None
        Username, password hash, and session revision.
    """
    with Session(storage.engine()) as database:
        row = database.get(storage.AppSetting, 'admin')
        return json.loads(row.value) if row else None


def _save(username: str, password: str) -> dict:
    """Validate and persist one salted password hash."""
    if not isinstance(username, str) or not 3 <= len(username.strip()) <= 64:
        raise ValidationError(ValidationMessage.USERNAME_LENGTH)
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise ValidationError(ValidationMessage.PASSWORD_LENGTH)
    value = {'username': username.strip(), 'password_hash': generate_password_hash(password, method=HASH_METHOD),
             'revision': secrets.token_hex(16)}
    with Session(storage.engine()) as database:
        row = database.get(storage.AppSetting, 'admin')
        if row:
            row.value = json.dumps(value)
        else:
            database.add(storage.AppSetting(key='admin', value=json.dumps(value)))
        database.commit()
    return value


def reset_password(password: str) -> None:
    """Reset the admin password from the local console.

    Parameters
    ----------
    password : str
        Replacement password, entered without echoing it.
    """
    with _lock:
        current = account()
        if current is None:
            raise ValueError('Create the admin account in the browser first.')
        _save(current['username'], password)


def startup_url(base_url: str) -> str:
    """Return the normal login address or a one-time setup link.

    Parameters
    ----------
    base_url : str
        Application browser address.

    Returns
    -------
    str
        Browser URL for this installation.
    """
    return base_url + ('/login' if account() else '/setup?token=' + SETUP_TOKEN)


def _signed_in(request: Request, current: dict | None) -> bool:
    """Validate a session against the current password revision."""
    return bool(current and request.session.get('admin_revision') == current['revision'])


def _next_url(request: Request) -> str:
    """Keep login redirects on this application's origin."""
    target = request.query_params.get('next', '')
    if any(ord(character) < 32 or ord(character) == 127 for character in target):
        return request.app.url_path_for('home')
    try:
        parts = urlsplit(target)
    except ValueError:
        return request.app.url_path_for('home')
    return target if (target.startswith('/') and not target.startswith('//') and
                      '\\' not in target and not parts.scheme and not parts.netloc) else '/'


def _login(request: Request, current: dict) -> None:
    """Replace pre-login session state to prevent session fixation."""
    request.session.clear()
    request.session['admin_revision'] = current['revision']


@router.api_route('/setup', methods=['GET', 'POST', 'HEAD'], name='admin.setup', response_model=None)
def setup(request: Request, form=Depends(read_form)):
    """Create the only administrator using the installation's setup link.

    Returns
    -------
    Response or str
        Setup form, validation result, or dashboard redirect.
    """
    with _lock:
        if account():
            return RedirectResponse(request.app.url_path_for(LOGIN_ENDPOINT), status_code=302)
        token = request.query_params.get('token', '')
        if token and hmac.compare_digest(token, SETUP_TOKEN):
            request.session['setup_authorized'] = True
            return RedirectResponse(request.app.url_path_for(SETUP_ENDPOINT), status_code=302)
        if not request.session.get('setup_authorized'):
            return render_template(request, AUTH_TEMPLATE, mode='setup-link', title='Secure setup', status_code=403)
        error = None
        if request.method == 'POST':
            try:
                if form.get('password') != form.get('confirm_password'):
                    raise ValidationError(ValidationMessage.PASSWORD_MISMATCH)
                current = _save(form.get('username', ''), form.get('password', ''))
            except ValidationError as exc:
                error = exc.reason.value
            except Exception as exc:
                get_logger(__name__).warning(f'Could not create the admin account ({type(exc).__name__})')
                return render_template(
                    request,
                    AUTH_TEMPLATE,
                    mode='setup',
                    title='Create your admin account',
                    error='Could not create the administrator account. Try again.',
                    status_code=500,
                )
            else:
                _login(request, current)
                return RedirectResponse(request.app.url_path_for('server_ui.server_page'), status_code=302)
        return render_template(
            request,
            AUTH_TEMPLATE,
            mode='setup',
            error=error,
            title='Create your admin account',
            username=form.get('username', 'admin'),
        )


@router.api_route('/login', methods=['GET', 'POST', 'HEAD'], name='admin.login', response_model=None)
def login(request: Request, form=Depends(read_form)):
    """Sign in with rate-limited, constant-work credential checks.

    Returns
    -------
    Response or str
        Login form, throttling response, or dashboard redirect.
    """
    current = account()
    if current is None:
        return RedirectResponse(request.app.url_path_for(SETUP_ENDPOINT), status_code=302)
    if _signed_in(request, current):
        return RedirectResponse(
            _next_url(request),
            status_code=302,
        )  # NOSONAR pythonsecurity:S5146: _next_url validates local paths.
    error = None
    if request.method == 'POST':
        # Serialize expensive hashes and bound memory used by failed-login counters.
        with _lock:
            now = time.monotonic()
            address = request.client.host if request.client else 'unknown'
            recent = [stamp for stamp in _attempts.get(address, []) if now - stamp < LOGIN_WINDOW]
            total = sum(sum(now - stamp < LOGIN_WINDOW for stamp in stamps) for stamps in _attempts.values())
            if len(recent) >= 5 or total >= 100:
                return render_template(
                    request,
                    AUTH_TEMPLATE,
                    mode='login',
                    error='Too many attempts. Try again in 15 minutes.',
                    title='Sign in',
                    username=form.get('username', ''),
                    status_code=429,
                    headers={'Retry-After': str(LOGIN_WINDOW)},
                )
            password = form.get('password', '')
            valid_password = check_password_hash(current['password_hash'], password[:256])
            valid_username = hmac.compare_digest(form.get('username', '').encode(),
                                                 current['username'].encode())
            if valid_password and valid_username and len(password) <= 256:
                _attempts.pop(address, None)
                _login(request, current)
                # _next_url rejects schemes, authorities, backslashes, and control characters.
                return RedirectResponse(
                    _next_url(request),
                    status_code=302,
                )  # NOSONAR pythonsecurity:S5146: Validated local redirect.
            _attempts[address] = recent + [now]
            _attempts.move_to_end(address)
            if len(_attempts) > 1024:
                _attempts.popitem(last=False)
            error = 'The username or password is incorrect.'
    return render_template(
        request,
        AUTH_TEMPLATE,
        mode='login',
        error=error,
        title='Sign in',
        username=form.get('username', ''),
    )


@router.api_route('/logout', methods=['POST'], name='admin.logout', response_model=None)
def logout(request: Request):
    """Clear the current authenticated session.

    Returns
    -------
    Response
        Login redirect.
    """
    request.session.clear()
    return RedirectResponse(request.app.url_path_for(LOGIN_ENDPOINT), status_code=302)


@router.api_route('/api/admin/password', methods=['POST'], name='admin.change_password', response_model=None)
def change_password(request: Request, form=Depends(read_form)):
    """Change the password and invalidate other signed-in sessions.

    Returns
    -------
    Response
        Password-change result.
    """
    with _lock:
        current = account()
        if not check_password_hash(current['password_hash'], form.get('current_password', '')[:256]):
            return JSONResponse({'message': 'The current password is incorrect.'}, status_code=400)
        if form.get('password') != form.get('confirm_password'):
            return JSONResponse({'message': ValidationMessage.PASSWORD_MISMATCH.value}, status_code=400)
        try:
            updated = _save(current['username'], form.get('password', ''))
        except ValidationError as exc:
            return JSONResponse({'message': exc.reason.value}, status_code=400)
        except Exception as exc:
            get_logger(__name__).warning(f'Could not change the admin password ({type(exc).__name__})')
            return JSONResponse({'message': 'Could not change the password. Try again.'}, status_code=500)
        _login(request, updated)
    return JSONResponse({'message': 'Password changed. Other sessions have been signed out.'})


def _require_admin(request: Request):
    """Reject private requests without a current admin session.

    Returns
    -------
    Response or tuple or None
        Login response, or no response when access is permitted.
    """
    path = request.url.path
    from jellyfin.connector import PUBLIC_PATHS
    if request.method in ('GET', 'HEAD') and path in PUBLIC_PATHS:
        return None
    if path in ('/login', '/setup', '/favicon.ico', '/status') or path.startswith(('/web/assets/', '/images/')):
        return None
    current = account()
    if not _signed_in(request, current):
        if path.startswith('/api/'):
            return JSONResponse({'message': 'Sign in to continue.'}, status_code=401)
        from urllib.parse import urlencode
        target = path + ('?' + request.url.query if request.url.query else '')
        return RedirectResponse('/login?' + urlencode({'next': target}), status_code=302)
    request.state.admin_username = current['username']
    return None


def _security_headers(request: Request, headers):
    """Apply security and cache headers to a browser response.

    Parameters
    ----------
    request : Request
        Request determining the applicable browser policy.
    headers : MutableHeaders
        Response headers updated in place.
    """
    headers['X-Frame-Options'] = 'DENY'
    headers['X-Content-Type-Options'] = 'nosniff'
    headers['Referrer-Policy'] = (
        'no-referrer' if request.url.path == '/setup' and request.query_params.get('token') else 'same-origin'
    )
    headers['Content-Security-Policy'] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; font-src 'self'; media-src 'self'; connect-src 'self'; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    )
    if request.url.path.startswith('/docs/'):
        headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net "
            "https://website-translator.app.crowdin.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net "
            "https://website-translator.app.crowdin.net; "
            "img-src 'self' data: https://cdn.jsdelivr.net https://website-translator.app.crowdin.net; "
            "font-src 'self' https://cdn.jsdelivr.net https://website-translator.app.crowdin.net; "
            "connect-src 'self' https://cdn.jsdelivr.net https://distributions.crowdin.net; "
            "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
        )
    if not request.url.path.startswith(('/web/assets/', '/images/')) and request.url.path != '/favicon.ico':
        headers['Cache-Control'] = 'no-store'


class BrowserSecurityMiddleware:
    """Protect signed sessions and bounded request bodies without buffering responses."""

    def __init__(self, app):
        """Wrap the next ASGI application in the middleware stack."""
        self.app = app

    async def __call__(self, scope, receive, send):
        """Apply authentication, CSRF validation, and security headers to HTTP traffic."""
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive)

        async def secure_send(message):
            if message['type'] == 'http.response.start':
                _security_headers(request, MutableHeaders(scope=message))
            await send(message)

        response = await run_in_threadpool(_require_admin, request)
        if response is not None:
            await response(scope, receive, secure_send)
            return
        try:
            body = await self._body(receive)
            sent = False

            async def replay_body():
                nonlocal sent
                if not sent:
                    sent = True
                    return {'type': 'http.request', 'body': body, 'more_body': False}
                return await receive()

            request = Request(scope, replay_body)
            await validate_csrf(request)
        except HTTPException as exc:
            response = await run_in_threadpool(error_response, request, exc.status_code, str(exc.detail))
            await response(scope, receive, secure_send)
            return

        # CSRF form parsing may consume the replay. The endpoint receives its own replay.
        sent = False
        await self.app(scope, replay_body, secure_send)

    @staticmethod
    async def _body(receive) -> bytes:
        """Enforce the 64 KiB limit even without a trustworthy Content-Length header."""
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                raise HTTPException(400, 'The request was interrupted.')
            chunk = message.get('body', b'')
            if len(body) + len(chunk) > 64 * 1024:
                raise HTTPException(413, 'Request body is too large.')
            body.extend(chunk)
            if not message.get('more_body', False):
                return bytes(body)
