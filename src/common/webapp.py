"""
src/common/webapp.py

Responsible for serving the webapp.
"""
# standard imports
import copy
import json
import os
from typing import Optional

# lib imports
from flask import Flask, Response
from flask import jsonify, render_template as flask_render_template, request, send_from_directory
from flask_babel import Babel
from flask_wtf import CSRFProtect
import polib
from werkzeug.utils import secure_filename

# local imports
import common
from common import config
from common import crypto
from common.definitions import Paths
from common import helpers
from common import locales
from common import logger
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
jinja_functions = dict(
    int=int,
    str=str,
)
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


@app.route('/')
@app.route('/home')
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


@app.route('/settings/', defaults={'configuration_spec': None})
@app.route('/settings/<path:configuration_spec>')
def settings(configuration_spec: Optional[str]) -> render_template:
    """
    Serve the configuration page page.

    .. todo:: This documentation needs to be improved.

    Parameters
    ----------
    configuration_spec : Optional[str]
        The spec to return. In the future this will be used to return config specs of plugins; however that is not
        currently implemented.

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

    if not configuration_spec:
        config_spec = config._CONFIG_SPEC_DICT
    else:
        # todo - handle plugin configs
        config_spec = None

    return render_template('config.html', title=_('Settings'), config_settings=config_settings, config_spec=config_spec)


@app.route('/docs/', defaults={'filename': 'index.html'})
@app.route('/docs/<path:filename>')
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


@app.route('/status')
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


@app.route('/test_logger')
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
    app.logger.info('testing from app.logger')
    app.logger.warning('testing from app.logger')
    app.logger.error('testing from app.logger')
    app.logger.critical('testing from app.logger')
    app.logger.debug('testing from app.logger')
    return f'Testing complete, check "logs/{__name__}.log" for output.'


@app.route('/api/settings', methods=['GET', 'POST'])
@app.route('/api/settings/<path:configuration_spec>')
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
    config_spec = config._CONFIG_SPEC_DICT

    if request.method == 'GET':
        return config.CONFIG
    if request.method == 'POST':
        boolean_dict = {
            'true': True,
            'false': False,
        }

        candidate = copy.deepcopy(config.CONFIG)
        decoded = config.decode_config(common.CONFIG)
        changed = []
        for option, value in request.form.items():
            key, separator, setting = option.partition('|')
            spec = config_spec.get(key, {}).get(setting)
            if not separator or not isinstance(spec, dict) or spec.get('locked'):
                return jsonify({'status': 'ERROR', 'message': 'Unknown or locked setting.'}), 400

            try:
                if spec['type'] == 'boolean':
                    value = boolean_dict[value.lower()]
                elif spec['type'] == 'float':
                    value = float(value)
                elif spec['type'] == 'integer':
                    value = int(value)
            except (KeyError, ValueError):
                return jsonify({'status': 'ERROR', 'message': 'Invalid setting value.'}), 400

            if decoded[key][setting] != value:
                changed.append((key, setting))
            if config.is_masked_field(section=key, key=setting):
                value = config.encode_value(value)
            candidate[key][setting] = value

        if not config.validate_config(config=candidate):
            return jsonify({'status': 'ERROR', 'message': 'Selected settings are not valid.'}), 400

        originals = {(key, setting): config.CONFIG[key][setting] for key, setting in changed}
        for key, setting in changed:
            config.CONFIG[key][setting] = candidate[key][setting]
        if not config.save_config(config=config.CONFIG):
            for (key, setting), value in originals.items():
                config.CONFIG[key][setting] = value
            return jsonify({'status': 'ERROR', 'message': 'Unable to save settings.'}), 500
        for key, setting in changed:
            on_change = config_spec[key][setting].get('on_change')
            if on_change:
                on_change()

        return jsonify({'status': 'OK', 'message': 'Selected settings are valid.'})


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
            data = dict()
            for entry in po:
                if entry.msgid:
                    data[entry.msgid] = entry.msgstr
                    app.logger.debug(f'Translation: {entry.msgid} -> {entry.msgstr}')

            return Response(response=json.dumps(data),
                            status=200,
                            mimetype='application/json')
