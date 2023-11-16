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
    from plexhints.constant_kit import CACHE_1DAY  # constant kit
    from plexhints.log_kit import Log  # log kit
    from plexhints.parse_kit import JSON  # parse kit
    from plexhints.prefs_kit import Prefs  # prefs kit

# lib imports
import flask
from flask import Flask, Response, render_template, send_from_directory
from flask_babel import Babel
import polib
from werkzeug.utils import secure_filename

# local imports
from constants import contributes_to, issue_urls, plugin_directory, plugin_identifier
import general_helper
from plex_api_helper import get_database_info, setup_plexapi
import themerr_db_helper
import tmdb_helper

# setup flask app
app = Flask(
    import_name=__name__,
    root_path=os.path.join(plugin_directory, 'Contents', 'Resources', 'web'),
    static_folder=os.path.join(plugin_directory, 'Contents', 'Resources', 'web'),
    template_folder=os.path.join(plugin_directory, 'Contents', 'Resources', 'web', 'templates')
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

app.config['BABEL_TRANSLATION_DIRECTORIES'] = os.path.join(plugin_directory, 'Contents', 'Strings')

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
    Prefs['bool_webapp_log_werkzeug_messages']
except KeyError:
    # this fails when building docs
    pass
else:
    if Prefs['bool_webapp_log_werkzeug_messages']:
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

    Examples
    --------
    >>> get_locale()
    en
    """
    return Prefs['enum_webapp_locale']


def start_server():
    # type: () -> bool
    """
    Start the flask server.

    The flask server is started in a separate thread to allow the plugin to continue running.

    Returns
    -------
    bool
        True if the server is running, otherwise False.

    Examples
    --------
    >>> start_server()

    See Also
    --------
    Core.Start : Function that starts the plugin.
    stop_server : Function that stops the webapp.
    """
    # use threading to start the flask app... or else web server seems to be killed after a couple of minutes
    flask_thread = Thread(
        target=app.run,
        kwargs=dict(
            host=Prefs['str_webapp_http_host'],
            port=Prefs['int_webapp_http_port'],
            debug=False,
            use_reloader=False  # reloader doesn't work when running in a separate thread
        )
    )

    # start flask application
    flask_thread.start()
    return flask_thread.is_alive()


def stop_server():
    # type: () -> bool
    """
    Stop the web server.

    This method currently does nothing.

    Returns
    -------
    bool
        True if the server was shutdown, otherwise False.

    Examples
    --------
    >>> stop_server()

    See Also
    --------
    start_server : Function that starts the webapp.
    """
    return False


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

    themerr_db_helper.update_cache()

    sections = plex_library.sections()

    items = dict()

    for section in sections:
        if section.agent not in contributes_to:
            # todo - there is a small chance that a library with an unsupported agent could still have
            # a individual items that was matched with a supported agent...
            continue  # skip unsupported metadata agents

        # get all the items in the section
        media_items = section.all()

        # get all items in the section with theme songs
        media_items_with_themes = section.all(theme__exists=True)

        # get all collections in the section
        collections = section.collections() if Prefs['bool_auto_update_collection_themes'] else []
        collections_with_themes = section.collections(theme__exists=True) if Prefs[
            'bool_auto_update_collection_themes'] else []

        # combine the items and collections into one list
        # this is done so that we can process both items and collections in the same loop
        all_items = media_items + collections

        # add each section to the items dict
        items[section.key] = dict(
            title=section.title,
            agent=section.agent,
            items=[],
            media_count=len(media_items),
            media_percent_complete=int(
                len(media_items_with_themes) / len(media_items) * 100) if len(media_items_with_themes) else 0,
            collection_count=len(collections),
            collection_percent_complete=int(
                len(collections_with_themes) / len(collections) * 100) if len(collections_with_themes) else 0,
            collections_enabled=Prefs['bool_auto_update_collection_themes'],
            total_count=len(all_items),
        )

        for item in all_items:
            # build the issue url
            database_info = get_database_info(item=item)
            database_type = database_info[0]
            database = database_info[1]
            item_agent = database_info[2]
            database_id = database_info[3]

            og_db = database
            og_db_id = database_id

            try:
                year = item.year
            except AttributeError:
                year = None

            # convert imdb id to tmdb id, so we can build the issue url properly
            if item.type == 'movie' and item_agent == 'com.plexapp.agents.imdb':
                # try to get tmdb id from imdb id
                tmdb_id = tmdb_helper.get_tmdb_id_from_imdb_id(imdb_id=database_id)
                if tmdb_id:
                    database_id = tmdb_id

            item_issue_url = None

            try:
                issue_url = issue_urls[database_type]
            except KeyError:
                issue_url = None

            if issue_url:
                if item.type == 'movie':
                    # override the id since ThemerrDB issues require the slug as part of the url
                    if item_agent == 'dev.lizardbyte.retroarcher-plex':
                        # get the slug and name from LizardByte db
                        try:
                            db_data = JSON.ObjectFromURL(
                                url='https://db.lizardbyte.dev/games/{}.json'.format(database_id),
                                cacheTime=CACHE_1DAY,
                                errors='strict'
                            )
                            issue_title = '{} ({})'.format(db_data['name'], year)
                            database_id = db_data['slug']
                        except Exception as e:
                            Log.Error('Error getting game data from LizardByte db: {}'.format(e))
                            issue_title = '{} ({})'.format(item.title, year)
                            database_id = None
                    else:
                        issue_title = '{} ({})'.format(item.title, year)
                else:  # collections
                    issue_title = item.title

                    # override the id since ThemerrDB issues require the slug as part of the url
                    if item_agent == 'dev.lizardbyte.retroarcher-plex':
                        # get the slug and name from LizardByte db
                        try:
                            db_data = JSON.ObjectFromURL(
                                url='https://db.lizardbyte.dev/{}/all.json'.format(
                                    database_type.rsplit('_', 1)[-1]),
                                cacheTime=CACHE_1DAY,
                                errors='strict'
                            )
                            issue_title = db_data[str(database_id)]['name']
                            database_id = db_data[str(database_id)]['slug']
                        except Exception as e:
                            Log.Error('Error getting collection data from LizardByte db: {}'.format(e))
                            database_id = None

                item_issue_url = issue_url.format(issue_title, database_id if database_id else '')

            if database_type and themerr_db_helper.item_exists(
                    database_type=database_type,
                    database=og_db,
                    id=og_db_id,
            ):
                issue_action = 'edit'
            else:
                issue_action = 'add'

            if item.theme:
                theme_status = 'complete'

                selected = (theme for theme in item.themes() if theme.selected).next()
                user_provided = (getattr(selected, 'provider', None) == 'local')

                if user_provided:
                    themerr_provided = False
                else:
                    themerr_data = general_helper.get_themerr_json_data(item=item)
                    themerr_provided = True if themerr_data else False
            else:
                if issue_action == 'edit':
                    theme_status = 'failed'
                else:
                    theme_status = 'missing'

                user_provided = False
                themerr_provided = False

            items[section.key]['items'].append(dict(
                title=item.title,
                agent=item_agent,
                database=database,
                database_type=database_type,
                database_id=database_id,
                issue_action=issue_action,
                issue_url=item_issue_url,
                theme=True if item.theme else False,
                theme_status=theme_status,
                themerr_provided=themerr_provided,
                type=item.type,
                user_provided=user_provided,
                year=year,
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
