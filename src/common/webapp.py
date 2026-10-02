"""
src/common/webapp.py

Responsible for serving the webapp.
"""
# standard imports
import copy
from functools import lru_cache
import hashlib
import json
import os
import time

# lib imports
from flask import Flask, Response, make_response as _make_response, session
from flask import jsonify, render_template as flask_render_template, request, send_from_directory, url_for
from flask_babel import Babel
from flask_wtf import CSRFProtect
from plexapi import exceptions as plex_exceptions
import polib
import requests
from werkzeug.utils import secure_filename

# local imports
import common
from common import admin, server_ui
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

# localization
_ = locales.get_text()

responses = {
    500: Response(response='Internal Server Error', status=500, mimetype='text/plain')
}

# mime type map
mime_type_map = {
    'gif': 'image/gif',
    'ico': 'image/vnd.microsoft.icon',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'png': 'image/png',
    'svg': 'image/svg+xml',
}

# setup flask app
app = Flask(
    import_name=__name__,
    root_path=os.path.join(Paths.ROOT_DIR, 'web'),
    static_folder=os.path.join(Paths.ROOT_DIR, 'web', 'assets'),
    static_url_path='/web/assets',
    template_folder=os.path.join(Paths.ROOT_DIR, 'web', 'templates'),
)
app.secret_key = os.urandom(32)

# remove extra lines rendered jinja templates
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True

# add python builtins to jinja templates
jinja_functions = {
    'int': int,
    'str': str,
}
app.jinja_env.globals.update(jinja_functions)


@lru_cache(maxsize=8)
def _asset_version(path: str, modified: int, size: int) -> str:
    """Cache a content fingerprint until a browser asset changes on disk."""
    with open(path, 'rb') as asset:
        return hashlib.file_digest(asset, 'sha256').hexdigest()[:16]


def asset_url(filename: str) -> str:
    """Return a browser asset URL that changes when its compiled contents change.

    Reuse the content fingerprint while the file's size and modification time are
    unchanged. Missing files retain their normal URL so the browser can report them.

    Parameters
    ----------
    filename : str
        Compiled asset name supplied by the application template.

    Returns
    -------
    str
        Same-origin URL with a content fingerprint when the asset exists.

    Examples
    --------
    >>> with app.test_request_context():
    ...     asset_url('app.css').startswith('/web/assets/app.css')
    True
    """
    path = os.path.join(app.static_folder, filename)
    try:
        stat = os.stat(path)
        version = _asset_version(path, stat.st_mtime_ns, stat.st_size)
    except OSError:
        version = None
    return url_for('static', filename=filename, v=version)


app.jinja_env.globals['asset_url'] = asset_url

# localization
babel = Babel(
    app=app,
    default_locale=locales.default_locale,
    default_timezone=locales.default_timezone,
    default_translation_directories=Paths.LOCALE_DIR,
    default_domain=locales.default_domain,
    configure_jinja=True,
    locale_selector=locales.get_locale
)

# setup logging for flask
log_handlers = logger.get_logger(name=__name__).handlers

for handler in log_handlers:
    app.logger.addHandler(handler)

admin.init_app(app)
app.register_blueprint(server_ui.blueprint)

csrf = CSRFProtect()
csrf.init_app(app)

PLEX_LOGIN_LIFETIME = 600


def render_template(template_name_or_list, **context):
    """
    Render a template, while providing our default context.

    This function is a wrapper around ``flask.render_template``.
    Our UI config is added to the template context.
    In the future, this function may be used to add other default contexts to templates.

    Parameters
    ----------
    template_name_or_list : str
        The name of the template to render.
    **context
        The context to pass to the template.

    Returns
    -------
    render_template
        The rendered template.

    Examples
    --------
    >>> render_template(template_name_or_list='home.html', title=_('Home'))
    """

    return flask_render_template(template_name_or_list=template_name_or_list, **context)


@app.route('/home', methods=['GET'])
@app.route('/', methods=['GET'])
def home() -> render_template:
    """
    Serve the webapp home page.

    Show cached Plex library data once it is available. Until then, show a progress page.

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
    >>> home()
    """
    try:
        items, errors, stats = server_ui.dashboard()
    except Exception:
        app.logger.exception('Unable to load dashboard')
        return render_template('error.html', title='Unable to load libraries',
                               message='The dashboard could not be loaded. Try again or check the log.'), 500
    return render_template('home.html', title='Overview', items=items, theme_errors=errors, stats=stats,
                           servers=server_ui.servers.list_servers())


def _stream_theme_audio(upstream: requests.Response, rating_key: int):
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
    try:
        yield from upstream.iter_content(chunk_size=64 * 1024)
    except requests.RequestException as error:
        app.logger.warning('Theme playback interrupted for rating_key=%s (%s)', rating_key, type(error).__name__)
    finally:
        upstream.close()


@app.route('/api/themes/<int:rating_key>', defaults={'server_id': 'default'}, methods=['GET'])
@app.route('/api/servers/<server_id>/themes/<int:rating_key>', methods=['GET'])
def play_theme(rating_key: int, server_id: str) -> Response:
    """Serve the item's current Plex theme without exposing the Plex token.

    Resolve the selected audio from fresh Plex metadata and forward byte range requests
    so browsers can determine the duration. Only media response headers reach the browser.

    Parameters
    ----------
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
    >>> play_theme(rating_key=42)  # Flask invokes this for GET /api/themes/42
    <Response ...>
    """
    from plex import plexapi

    try:
        with storage.server_scope(server_id):
            server = plexapi.setup_plexapi()
        if server is None:
            return _make_response(jsonify({'message': 'Connect to Plex before playing themes.'}), 503)
        item = server.fetchItem(rating_key)
        theme_path = getattr(item, 'theme', None)
        if not theme_path:
            return _make_response(jsonify({'message': 'This item has no theme.'}), 404)
        if not theme_path.startswith('/library/metadata/') or '/theme/' not in theme_path:
            return _make_response(jsonify({'message': 'Plex returned an unsupported theme path.'}), 502)

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
        return _make_response(jsonify({'message': 'This Plex item is no longer available.'}), 404)
    except (plex_exceptions.PlexApiException, OSError, ValueError) as error:
        app.logger.warning('Unable to load theme for rating_key=%s (%s)', rating_key, type(error).__name__)
        return _make_response(jsonify({'message': 'Unable to load theme audio from Plex.'}), 502)

    return _theme_audio_response(upstream, rating_key)


def _theme_audio_response(upstream: requests.Response, rating_key: int) -> Response:
    """Build a browser response and close rejected Plex audio streams.

    Parameters
    ----------
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
            return Response(status=416, headers=headers)
        status = 404 if upstream.status_code == 404 else 502
        app.logger.warning('Plex rejected theme playback for rating_key=%s (HTTP %s)', rating_key, upstream.status_code)
        return _make_response(jsonify({'message': 'Plex could not provide theme audio.'}), status)
    content_type = upstream.headers.get('Content-Type', 'application/octet-stream').split(';', 1)[0].lower()
    if not content_type.startswith('audio/') and content_type not in ('video/mp4', 'application/octet-stream'):
        upstream.close()
        return _make_response(jsonify({'message': 'Plex returned an unsupported audio format.'}), 502)
    headers['Content-Type'] = content_type
    if request.method == 'HEAD':
        upstream.close()
        return Response(status=upstream.status_code, headers=headers)

    response = Response(_stream_theme_audio(upstream, rating_key), status=upstream.status_code, headers=headers)
    response.call_on_close(upstream.close)
    return response


@app.route('/settings/', methods=['GET'])
def settings() -> render_template:
    """
    Serve the configuration page.

    Decode any masked settings for display and render the current configuration specification.

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
    >>> settings()
    """
    config_settings = config.decode_config(common.CONFIG)
    return render_template('config.html', title=_('Settings'), config_settings=config_settings,
                           config_spec=config._CONFIG_SPEC_DICT)


@app.route('/api/directories', methods=['POST'])
def browse_directories() -> Response:
    """List server directories for the configuration folder picker.

    The response contains directory names and paths, without file contents. The request is
    protected by the same CSRF check as other settings actions.

    Returns
    -------
    Response
        Current directory, parent directory, and child directories.

    Examples
    --------
    >>> browse_directories()  # Flask invokes this for POST /api/directories
    """
    payload = request.get_json(silent=True)
    requested = payload.get('path', '') if isinstance(payload, dict) else None
    if not isinstance(requested, str) or len(requested) > 4096 or '\x00' in requested:
        return _make_response(jsonify({'message': 'Invalid directory path.'}), 400)
    requested = requested or os.path.expanduser('~')
    if not os.path.isabs(requested):
        return _make_response(jsonify({'message': 'Directory path must be absolute.'}), 400)

    try:
        directory = os.path.realpath(requested)
        with os.scandir(directory) as entries:
            children = sorted(
                ({'name': entry.name, 'path': os.path.realpath(entry.path)}
                 for entry in entries if entry.is_dir()),
                key=lambda entry: entry['name'].casefold(),
            )
    except OSError:
        return _make_response(jsonify({'message': 'Directory is unavailable.'}), 400)

    parent = os.path.dirname(directory)
    return jsonify({'path': directory, 'parent': parent if parent != directory else None, 'directories': children})


@app.route('/docs/', defaults={'filename': 'index.html'}, methods=['GET'])
@app.route('/docs/<path:filename>', methods=['GET'])
def docs(filename) -> send_from_directory:
    """
    Serve the Sphinx html documentation.

    Resolve the requested page from the built documentation directory.

    Parameters
    ----------
    filename : str
        Path to an HTML documentation file relative to the built documentation directory.

    Returns
    -------
    flask.send_from_directory
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

    return send_from_directory(directory=os.path.join(Paths.DOCS_DIR), path=filename)


@app.route(
    '/favicon.ico',
    defaults={'img': 'favicon.ico'},
    methods=['GET'],
)
@app.route("/images/<path:img>", methods=["GET"])
def image(img: str) -> send_from_directory:
    """
    Get image from static/images directory.

    Serve images from the static/images directory.

    Parameters
    ----------
    img : str
        The image to return.

    Returns
    -------
    flask.send_from_directory
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
            return send_from_directory(directory=directory, path=filename, mimetype=mime_type_map[file_extension])
        else:
            return Response(response='Invalid file type', status=400, mimetype='text/plain')
    else:
        return Response(response='Image not found', status=404, mimetype='text/plain')


@app.route('/status', methods=['GET'])
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


@app.route('/test_logger', methods=['POST'])
def test_logger() -> str:
    """
    Test logging functions.

    Check `./logs/common.webapp.log` for output.

    Returns
    -------
    str
        A message telling the user to check the logs.

    Notes
    -----
    The following routes trigger this function.

        `/test_logger`

    Examples
    --------
    >>> test_logger()
    """
    message = 'testing from app.logger'
    app.logger.info(message)
    app.logger.warning(message)
    app.logger.error(message)
    app.logger.critical(message)
    app.logger.debug(message)
    return f'Testing complete, check "logs/{__name__}.log" for output.'


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


def _candidate_settings() -> tuple[dict, list[tuple[str, str]], Response | None]:
    """Build a validated candidate from the submitted settings form.

    Returns
    -------
    tuple[dict, list[tuple[str, str]], Response or None]
        Candidate configuration, changed keys, and an error response if parsing failed.
    """
    candidate = copy.deepcopy(config.CONFIG)
    decoded = config.decode_config(common.CONFIG)
    changed = []
    for option, value in request.form.items():
        try:
            key, setting, value = _parse_setting(option, value)
        except KeyError:
            error = _make_response(jsonify({'status': 'ERROR', 'message': 'Unknown or locked setting.'}), 400)
            return candidate, changed, error
        except ValueError:
            error = _make_response(jsonify({'status': 'ERROR', 'message': 'Invalid setting value.'}), 400)
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
        return _make_response(jsonify({'status': 'ERROR', 'message': 'Unable to save settings.'}), 500)
    for key, setting in changed:
        on_change = config._CONFIG_SPEC_DICT[key][setting].get('on_change')
        if on_change:
            on_change()
    if any(key == 'Themerr' and setting in (
            'BOOL_THEMERR_ENABLED', 'INT_UPDATE_THEMES_INTERVAL', 'INT_UPDATE_DATABASE_CACHE_INTERVAL',
    ) for key, setting in changed):
        from themerr import scheduled_tasks
        scheduled_tasks.configure_jobs()
    return jsonify({'status': 'OK', 'message': 'Selected settings are valid.'})


@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings() -> Response:
    """
    Get current settings or save changes to settings from the web ui.

    This endpoint accepts a `GET` or `POST` request. A `GET` request will return the current settings.
    A `POST` request will process the data passed in and return the results of processing.

    Returns
    -------
    Response
        A response formatted as ``flask.jsonify``.

    Examples
    --------
    >>> api_settings()
    <Response ... bytes [200 OK]>
    """
    if request.method == 'GET':
        return jsonify(config.CONFIG)

    candidate, changed, error = _candidate_settings()
    if error is not None:
        return error
    if not config.validate_config(config=candidate):
        return _make_response(jsonify({'status': 'ERROR', 'message': 'Selected settings are not valid.'}), 400)
    return _save_settings(candidate, changed)


@app.route('/api/plex/auth', methods=['GET'])
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
    return jsonify({'connected': bool(plex_auth.get_token())})


@app.route('/api/plex/auth/start', methods=['POST'])
def plex_auth_start() -> Response:
    """Start a Plex browser sign-in for this web session.

    Store the PIN in the browser session so it can be checked later.

    Returns
    -------
    Response
        Plex authorization URL or a sanitized error.

    Examples
    --------
    >>> plex_auth_start()
    <Response ...>
    """
    try:
        login = plex_auth.start_login()
    except (OSError, KeyError, TypeError, ValueError):
        app.logger.exception('Unable to start Plex sign-in')
        return _make_response(jsonify({'message': 'Unable to start Plex sign-in. Please try again.'}), 502)

    session['plex_login'] = {'pin_id': login['pin_id'], 'code': login['code'], 'started': time.time()}
    return jsonify({'auth_url': login['auth_url']})


@app.route('/api/plex/auth/check', methods=['POST'])
def plex_auth_check() -> Response:
    """Finish a Plex sign-in once its PIN has been claimed.

    Keep the previous connection until the new token reaches the selected server.

    Returns
    -------
    Response
        Pending, connected, expired, or error status.

    Examples
    --------
    >>> plex_auth_check()
    <Response ...>
    """
    login = session.get('plex_login')
    if not login:
        return _make_response(jsonify({'message': 'Start Plex sign-in first.'}), 400)
    if time.time() - login['started'] > PLEX_LOGIN_LIFETIME:
        session.pop('plex_login', None)
        return _make_response(jsonify({'message': 'Plex sign-in expired. Please try again.'}), 410)

    try:
        token = plex_auth.check_login(pin_id=login['pin_id'], code=login['code'])
    except requests.HTTPError as error:
        if error.response is not None and error.response.status_code in (404, 410):
            session.pop('plex_login', None)
            return _make_response(jsonify({'message': 'Plex sign-in expired. Please try again.'}), 410)
        app.logger.warning('Unable to check Plex sign-in: %s', error)
        return _make_response(jsonify({'message': 'Unable to check Plex sign-in. Please try again.'}), 502)
    except (requests.RequestException, KeyError, TypeError, ValueError):
        app.logger.exception('Unable to check Plex sign-in')
        return _make_response(jsonify({'message': 'Unable to check Plex sign-in. Please try again.'}), 502)

    if not token:
        return _make_response(jsonify({'connected': False}), 202)

    try:
        plex_auth.set_token(token)
    except OSError:
        app.logger.exception('Unable to save Plex sign-in')
        return _make_response(jsonify({'message': 'Unable to save Plex sign-in.'}), 500)
    session.pop('plex_login', None)
    return jsonify({'connected': True})


@app.route('/api/plex/auth/disconnect', methods=['POST'])
def plex_auth_disconnect() -> Response:
    """Remove the local Plex connection.

    Clear the saved token and stop the active event listener.

    Returns
    -------
    Response
        Disconnected status.

    Examples
    --------
    >>> plex_auth_disconnect()
    <Response ...>
    """
    try:
        server_ui.servers.disconnect_account()
    except OSError:
        app.logger.exception('Unable to disconnect Plex')
        return _make_response(jsonify({'message': 'Unable to disconnect Plex.'}), 500)

    from plex import plexapi
    plexapi.stop_plex_listener()
    server_ui.servers.clear_connections()
    plexapi.plex_server = None
    session.pop('plex_login', None)
    return jsonify({'connected': False})


def start_webapp():
    """
    Start the webapp.

    Start the flask webapp. This is placed in it's own function to allow the ability to start the webapp within a
    thread in a simple way.

    Examples
    --------
    >>> start_webapp()
     * Serving Flask app 'common.webapp' (lazy loading)
    ...
     * Running on https://.../ (Press CTRL+C to quit)

    >>> from common import webapp, threads
    >>> threads.run_in_thread(target=webapp.start_webapp, name='Flask', daemon=True).start()
     * Serving Flask app 'common.webapp' (lazy loading)
    ...
     * Running on https://.../ (Press CTRL+C to quit)
    """
    global URL, URL_SCHEME
    URL_SCHEME = 'https' if config.CONFIG['Network']['SSL'] else 'http'
    URL = f"{URL_SCHEME}://127.0.0.1:{config.CONFIG['Network']['HTTP_PORT']}"
    app.config['SESSION_COOKIE_SECURE'] = bool(config.CONFIG['Network']['SSL'])

    if config.CONFIG['Network']['SSL']:
        cert_file, key_file = crypto.initialize_certificate()
    else:
        cert_file = key_file = None

    app.run(
        host=config.CONFIG['Network']['HTTP_HOST'],
        port=config.CONFIG['Network']['HTTP_PORT'],
        debug=common.DEV,
        use_debugger=False,
        ssl_context=(cert_file, key_file) if config.CONFIG['Network']['SSL'] else None,
        use_reloader=False  # reloader doesn't work when running in a separate thread
    )


@app.route("/translations", methods=["GET"])
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
    locale = locales.get_locale()

    po_files = [
        f'{Paths.LOCALE_DIR}/{locale}/LC_MESSAGES/{locales.default_domain}.po',  # selected locale
        f'{Paths.LOCALE_DIR}/{locales.default_domain}.po',  # fallback to default domain
    ]

    for po_file in po_files:
        if os.path.isfile(po_file):
            po = polib.pofile(po_file)

            # convert the po to json
            data = {}
            for entry in po:
                if entry.msgid:
                    data[entry.msgid] = entry.msgstr
                    app.logger.debug(f'Translation: {entry.msgid} -> {entry.msgstr}')

            return Response(response=json.dumps(data),
                            status=200,
                            mimetype='application/json')


@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(413)
@app.errorhandler(500)
def browser_error(error):
    """Return useful errors without disclosing exception details.

    API callers receive JSON; browser pages receive the workspace error view.

    Parameters
    ----------
    error : HTTPException
        HTTP failure raised by Flask or CSRF protection.

    Returns
    -------
    Response or tuple
        JSON for an API caller, or the redesigned error page.

    Examples
    --------
    >>> browser_error(error)  # Flask invokes this for an HTTP error
    (..., 404)
    """
    code = error.code
    messages = {400: 'Your session or form expired. Reload the page and try again.',
                404: 'This page is unavailable.'}
    message = messages.get(code, 'The request could not be completed.')
    if request.path.startswith('/api/'):
        return jsonify({'message': message}), code
    return render_template('error.html', title=str(code), message=message), code
