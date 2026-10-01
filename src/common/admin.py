"""Single-administrator authentication and browser security boundaries."""

# standard imports
from collections import OrderedDict
from datetime import timedelta
import hmac
import json
import logging
import secrets
from threading import RLock
import time
from urllib.parse import urlsplit

# lib imports
from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash

# local imports
from common import config
from themerr import storage

blueprint = Blueprint('admin', __name__)
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
        raise ValueError('Use a username between 3 and 64 characters.')
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise ValueError('Use a password between 12 and 256 characters.')
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


def _signed_in(current: dict | None) -> bool:
    """Validate a session against the current password revision."""
    return bool(current and session.get('admin_revision') == current['revision'])


def _next_url() -> str:
    """Keep login redirects on this application's origin."""
    target = request.args.get('next', '')
    try:
        parts = urlsplit(target)
    except ValueError:
        return url_for('home')
    return target if (target.startswith('/') and not target.startswith('//') and
                      '\\' not in target and not parts.scheme and not parts.netloc) else url_for('home')


def _login(current: dict) -> None:
    """Replace pre-login session state to prevent session fixation."""
    session.clear()
    session['admin_revision'] = current['revision']
    session.permanent = True


@blueprint.route('/setup', methods=['GET', 'POST'])
def setup():
    """Create the only administrator using the installation's setup link.

    Returns
    -------
    Response or str
        Setup form, validation result, or dashboard redirect.
    """
    with _lock:
        if account():
            return redirect(url_for('admin.login'))
        token = request.args.get('token', '')
        if token and hmac.compare_digest(token, SETUP_TOKEN):
            session['setup_authorized'] = True
            return redirect(url_for('admin.setup'))
        if not session.get('setup_authorized'):
            return render_template('auth.html', mode='setup-link', title='Secure setup'), 403
        error = None
        if request.method == 'POST':
            try:
                if request.form.get('password') != request.form.get('confirm_password'):
                    raise ValueError('The passwords do not match.')
                current = _save(request.form.get('username', ''), request.form.get('password', ''))
            except ValueError as exc:
                error = str(exc)
            else:
                _login(current)
                return redirect(url_for('server_ui.server_page'))
        return render_template('auth.html', mode='setup', error=error, title='Create your admin account')


@blueprint.route('/login', methods=['GET', 'POST'])
def login():
    """Sign in with rate-limited, constant-work credential checks.

    Returns
    -------
    Response or str
        Login form, throttling response, or dashboard redirect.
    """
    current = account()
    if current is None:
        return redirect(url_for('admin.setup'))
    if _signed_in(current):
        return redirect(_next_url())
    error = None
    if request.method == 'POST':
        # Serialize expensive hashes and bound memory used by failed-login counters.
        with _lock:
            now = time.monotonic()
            address = request.remote_addr or 'unknown'
            recent = [stamp for stamp in _attempts.get(address, []) if now - stamp < LOGIN_WINDOW]
            total = sum(sum(now - stamp < LOGIN_WINDOW for stamp in stamps) for stamps in _attempts.values())
            if len(recent) >= 5 or total >= 100:
                return (render_template('auth.html', mode='login', error='Too many attempts. Try again in 15 minutes.',
                                        title='Sign in'), 429, {'Retry-After': str(LOGIN_WINDOW)})
            password = request.form.get('password', '')
            valid_password = check_password_hash(current['password_hash'], password[:256])
            valid_username = hmac.compare_digest(request.form.get('username', '').encode(),
                                                 current['username'].encode())
            if valid_password and valid_username and len(password) <= 256:
                _attempts.pop(address, None)
                _login(current)
                return redirect(_next_url())
            _attempts[address] = recent + [now]
            _attempts.move_to_end(address)
            if len(_attempts) > 1024:
                _attempts.popitem(last=False)
            error = 'The username or password is incorrect.'
    return render_template('auth.html', mode='login', error=error, title='Sign in')


@blueprint.route('/logout', methods=['POST'])
def logout():
    """Clear the current authenticated session.

    Returns
    -------
    Response
        Login redirect.
    """
    session.clear()
    return redirect(url_for('admin.login'))


@blueprint.route('/api/admin/password', methods=['POST'])
def change_password():
    """Change the password and invalidate other signed-in sessions.

    Returns
    -------
    Response
        Password-change result.
    """
    with _lock:
        current = account()
        if not check_password_hash(current['password_hash'], request.form.get('current_password', '')[:256]):
            return jsonify({'message': 'The current password is incorrect.'}), 400
        if request.form.get('password') != request.form.get('confirm_password'):
            return jsonify({'message': 'The passwords do not match.'}), 400
        try:
            updated = _save(current['username'], request.form.get('password', ''))
        except ValueError as exc:
            return jsonify({'message': str(exc)}), 400
        _login(updated)
    return jsonify({'message': 'Password changed. Other sessions have been signed out.'})


def init_app(app) -> None:
    """Protect private routes and apply browser security headers.

    Parameters
    ----------
    app : Flask
        Web application to protect.
    """
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=12), MAX_CONTENT_LENGTH=64 * 1024)
    app.register_blueprint(blueprint)
    logging.getLogger('werkzeug').addFilter(_SetupLinkFilter())

    @app.before_request
    def require_admin():
        # Flask confines public assets to the compiled assets directory.
        if request.endpoint == 'static':
            return None
        if request.endpoint in ('admin.login', 'admin.setup', 'image', 'status'):
            return None
        if not _signed_in(account()):
            if request.path.startswith('/api/'):
                return jsonify({'message': 'Sign in to continue.'}), 401
            return redirect(url_for('admin.login', next=request.full_path.rstrip('?')))
        return None

    @app.after_request
    def security_headers(response):
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = (
            'no-referrer' if request.endpoint == 'admin.setup' and request.args.get('token') else 'same-origin'
        )
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self'; media-src 'self'; connect-src 'self'; "
            "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
        )
        if request.endpoint != 'static' and request.endpoint != 'image':
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.context_processor
    def admin_context():
        current = account()
        return {'admin_username': current['username'] if _signed_in(current) else None}

    # Set before the server accepts its first request; no mutation of cookie policy per request.
    app.config['SESSION_COOKIE_SECURE'] = bool(config.CONFIG and config.CONFIG['Network']['SSL'])
