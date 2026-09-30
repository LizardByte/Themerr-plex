"""
src/common/webapp.py

Responsible for serving the webapp.
"""
# standard imports
import copy
import json
import os
import time

# lib imports
from flask import Flask, Response, make_response as _make_response, session
from flask import jsonify, render_template as flask_render_template, request, send_from_directory
from flask_babel import Babel
from flask_wtf import CSRFProtect
import polib
import requests
from werkzeug.utils import secure_filename

# local imports
import common
from common import config
from common import crypto
from common.definitions import Paths
from common import helpers
from common import locales
from common import logger
from plex import auth as plex_auth
from themerr.cache import database_cache_file

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
    static_folder=os.path.join(Paths.ROOT_DIR, 'web'),
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
    context['ui_config'] = common.CONFIG['User_Interface'].copy()

    return flask_render_template(template_name_or_list=template_name_or_list, **context)


@app.route('/', methods=['GET'])
@app.route('/home', methods=['GET'])
def home() -> render_template:
    """
    Serve the webapp home page.

    .. todo:: This documentation needs to be improved.

    Returns
    -------
    render_template
        The rendered page.

    Notes
    -----
    The following routes trigger this function.

        `/`
        `/home`

    Examples
    --------
    >>> home()
    """
    if not os.path.isfile(database_cache_file):
        return render_template('home_db_not_cached.html', title='Home')

    try:
        items = json.loads(helpers.file_load(filename=database_cache_file, binary=False))
    except IOError:
        return responses[500]

    return render_template('home.html', title=_('Home'), items=items)


@app.route('/settings/', methods=['GET'])
def settings() -> render_template:
    """
    Serve the configuration page.

    .. todo:: This documentation needs to be improved.

    Returns
    -------
    render_template
        The rendered page.

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


@app.route('/docs/', defaults={'filename': 'index.html'}, methods=['GET'])
@app.route('/docs/<path:filename>', methods=['GET'])
def docs(filename) -> send_from_directory:
    """
    Serve the Sphinx html documentation.

    .. todo:: This documentation needs to be improved.

    Parameters
    ----------
    filename : str
        The html filename to return.

    Returns
    -------
    flask.send_from_directory
        The requested documentation page.

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
    directory = os.path.join(app.static_folder, 'images')
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


@app.route('/test_logger', methods=['GET'])
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

    from plex import plexapi
    try:
        server = plexapi.connect_plex_server(plex_url=config.CONFIG['Plex']['PLEX_URL'], plex_token=token)
    except Exception:
        app.logger.exception('Plex sign-in succeeded, but the selected server could not be reached')
        return _make_response(jsonify({
            'message': 'Signed in to Plex, but could not connect to the configured Plex server.',
        }), 400)

    try:
        plex_auth.set_token(token)
    except OSError:
        app.logger.exception('Unable to save Plex sign-in')
        return _make_response(jsonify({'message': 'Unable to save Plex sign-in.'}), 500)

    plexapi.plex_server = server
    try:
        plexapi.plex_listener()
    except Exception:
        app.logger.exception('Plex sign-in succeeded, but the event listener could not start')
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
        plex_auth.disconnect()
    except OSError:
        app.logger.exception('Unable to disconnect Plex')
        return _make_response(jsonify({'message': 'Unable to disconnect Plex.'}), 500)

    from plex import plexapi
    plexapi.stop_plex_listener()
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

    if config.CONFIG['Network']['SSL']:
        cert_file, key_file = crypto.initialize_certificate()
    else:
        cert_file = key_file = None

    app.run(
        host=config.CONFIG['Network']['HTTP_HOST'],
        port=config.CONFIG['Network']['HTTP_PORT'],
        debug=common.DEV,
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
        f'{Paths.LOCALE_DIR}/{locale}/LC_MESSAGES/themerr-plex.po',  # selected locale
        f'{Paths.LOCALE_DIR}/themerr-plex.po',  # fallback to default domain
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
