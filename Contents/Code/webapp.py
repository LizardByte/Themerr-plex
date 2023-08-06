# -*- coding: utf-8 -*-

# future imports
from __future__ import division  # fix float division for python2

# standard imports
import json
import logging
import os
from threading import Thread

# plex debugging
try:
    import plexhints  # noqa: F401
except ImportError:
    pass
else:  # the code is running outside of Plex
    from plexhints.core_kit import Core  # core kit
    from plexhints.log_kit import Log  # log kit
    from plexhints.prefs_kit import Prefs  # prefs kit

# lib imports
import flask
from flask import Flask, Response, render_template, request, send_from_directory
from flask_babel import Babel
import polib
from werkzeug.utils import secure_filename

# local imports
from constants import contributes_to, issue_url_games, issue_url_movies, plugin_identifier
from plex_api_helper import get_database_id, get_theme_upload_path, setup_plexapi

bundle_path = Core.bundle_path
if bundle_path.endswith('test.bundle'):
    # use current directory instead, to allow for testing outside of Plex
    bundle_path = os.getcwd()

# setup flask app
app = Flask(
    import_name=__name__,
    root_path=os.path.join(bundle_path, 'Contents', 'Resources', 'web'),
    static_folder=os.path.join(bundle_path, 'Contents', 'Resources', 'web'),
    template_folder=os.path.join(bundle_path, 'Contents', 'Resources', 'web', 'templates')
    )

# remove extra lines rendered jinja templates
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True

# localization
babel = Babel(
    app=app,
    default_locale='en',
    default_timezone='UTC',
    default_domain='themerr-plex',
    configure_jinja=True
)

app.config['BABEL_TRANSLATION_DIRECTORIES'] = os.path.join(bundle_path, 'Contents', 'Strings')

# setup logging for flask
Log.Info('Adding flask log handlers to plex plugin logger')

# get the plugin logger
plugin_logger = logging.getLogger(plugin_identifier)

# replace the app.logger handlers with the plugin logger handlers
app.logger.handlers = plugin_logger.handlers
app.logger.setLevel(plugin_logger.level)

# test message
app.logger.info('flask app logger test message')

try:
    Prefs['bool_log_werkzeug_messages']
except KeyError:
    # this fails when building docs
    pass
else:
    if Prefs['bool_log_werkzeug_messages']:
        # get the werkzeug logger
        werkzeug_logger = logging.getLogger('werkzeug')

        # replace the werkzeug logger handlers with the plugin logger handlers
        werkzeug_logger.handlers = plugin_logger.handlers

        # use the same log level as the plugin logger
        werkzeug_logger.setLevel(plugin_logger.level)

        # test message
        werkzeug_logger.info('werkzeug logger test message')


# mime type map
mime_type_map = {
    'gif': 'image/gif',
    'ico': 'image/vnd.microsoft.icon',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'png': 'image/png',
    'svg': 'image/svg+xml',
}


@babel.localeselector
def get_locale():
    # type: () -> str
    """
    Get the locale from the config.

    Get the locale specified in the config. This does not need to be called as it is done so automatically by `babel`.

    Returns
    -------
    str
        The locale.

    See Also
    --------
    pyra.locales.get_locale : Use this function instead.

    Examples
    --------
    >>> get_locale()
    en
    """
    return Prefs['enum_locale']


def start_server():
    # use threading to start the flask app... or else web server seems to be killed after a couple of minutes
    flask_thread = Thread(
        target=app.run,
        kwargs=dict(
            host=Prefs['str_http_host'],
            port=Prefs['int_http_port'],
            debug=False,
            use_reloader=False  # reloader doesn't work when running in a separate thread
        )
    )

    # start flask application
    flask_thread.start()


def stop_server():
    # stop flask server
    # todo - this doesn't work
    request.environ.get('werkzeug.server.shutdown')


@app.route('/', methods=["GET"])
@app.route('/home', methods=["GET"])
def home():
    # type: () -> render_template
    """
    Serve the webapp home page.

    This page serves the Themerr completion report for supported Plex libraries.

    Returns
    -------
    render_template
        The rendered page.

    Notes
    -----
    The following routes trigger this function.

        - `/`
        - `/home`

    Examples
    --------
    >>> home()
    """
    # get all Plex items from supported metadata agents
    plex_server = setup_plexapi()
    plex_library = plex_server.library

    sections = plex_library.sections()

    items = dict()

    for section in sections:
        if section.agent not in contributes_to:
            # todo - there is a small chance that a library with an unsupported agent could still have
            # a individual items that was matched with a supported agent...
            continue  # skip unsupported metadata agents

        # get all items in the section
        all_items = section.all()

        # get all items in the section with theme songs
        items_with_themes = section.all(theme__exists=True)

        # add each section to the items dict
        items[section.key] = dict(
            title=section.title,
            agent=section.agent,
            items=[],
            percent_complete=int(len(items_with_themes) / len(all_items) * 100) if len(items_with_themes) else 0
        )

        for item in all_items:
            # build the issue url
            database_info = get_database_id(item=item)
            item_agent = database_info[0]
            database_id = database_info[1]

            item_issue_url = None
            if item_agent == 'dev.lizardbyte.retroarcher-plex':
                issue_url = issue_url_games
            elif item_agent in contributes_to:
                issue_url = issue_url_movies
            else:
                issue_url = None

            if issue_url:
                issue_title = '%s (%s)' % (item.title, item.year)
                item_issue_url = issue_url % (issue_title, database_id)

            theme_status = 'missing'  # default status
            issue_action = 'add'  # default action

            if item.theme:
                theme_status = 'complete'
                issue_action = 'edit'

                theme_upload_path = get_theme_upload_path(plex_item=item)
                if not os.path.isdir(theme_upload_path) or not os.listdir(theme_upload_path):
                    theme_status = 'error'
                    issue_action = 'add'

            items[section.key]['items'].append(dict(
                title=item.title,
                agent=item_agent,
                database_id=database_id,
                issue_action=issue_action,
                issue_url=item_issue_url,
                theme=True if item.theme else False,
                theme_status=theme_status,
                year=item.year,
            ))

    return render_template('home.html', title='Home', items=items)


@app.route("/<path:img>", methods=["GET"])
def image(img):
    # type: (str) -> flask.send_from_directory
    """
    Get image from static/images directory.

    Returns
    -------
    flask.send_from_directory
        The image.

    Notes
    -----
    The following routes trigger this function.

        - `/favicon.ico`

    Examples
    --------
    >>> image('favicon.ico')
    """
    directory = os.path.join(app.static_folder, 'images')
    filename = os.path.basename(secure_filename(filename=img))  # sanitize the input

    if os.path.isfile(os.path.join(directory, filename)):
        file_extension = filename.rsplit('.', 1)[-1]
        if file_extension in mime_type_map:
            return send_from_directory(directory=directory, filename=filename, mimetype=mime_type_map[file_extension])
        else:
            return Response(response='Invalid file type', status=400, mimetype='text/plain')
    else:
        return Response(response='Image not found', status=404, mimetype='text/plain')


@app.route('/status', methods=["GET"])
def status():
    # type: () -> dict
    """
    Check the status of Themerr-plex.

    This can be used to test if the plugin is still running. It could be used as part of a healthcheck for Docker,
    and may have many other uses in the future.

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


@app.route("/translations", methods=["GET"])
def translations():
    # type: () -> Response
    """
    Serve the translations.

    Returns
    -------
    Response
        The translations.

    Examples
    --------
    >>> translations()
    """
    locale = get_locale()

    po_files = [
        '%s/%s/LC_MESSAGES/themerr-plex.po' % (app.config['BABEL_TRANSLATION_DIRECTORIES'], locale),  # selected locale
        '%s/themerr-plex.po' % app.config['BABEL_TRANSLATION_DIRECTORIES'],  # fallback to default domain
    ]

    for po_file in po_files:
        if os.path.isfile(po_file):
            po = polib.pofile(po_file)

            # convert the po to json
            data = dict()
            for entry in po:
                if entry.msgid:
                    data[entry.msgid] = entry.msgstr
                    Log.Debug('Translation: %s -> %s' % (entry.msgid, entry.msgstr))

            return Response(response=json.dumps(data),
                            status=200,
                            mimetype='application/json')
