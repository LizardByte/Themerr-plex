# -*- coding: utf-8 -*-

# standard imports
import inspect
import re

# plex debugging
try:
    import plexhints  # noqa: F401
except ImportError:
    pass
else:  # the code is running outside of Plex
    from plexhints import plexhints_setup, update_sys_path
    plexhints_setup()  # read the plugin plist file and determine if plexhints should use elevated policy or not
    update_sys_path()  # when running outside plex, append the path

    from plexhints.agent_kit import Agent, Media  # agent kit
    from plexhints.decorator_kit import handler  # decorator kit
    from plexhints.locale_kit import Locale
    from plexhints.log_kit import Log  # log kit
    from plexhints.model_kit import MetadataModel  # model kit
    from plexhints.object_kit import MessageContainer, MetadataSearchResult, SearchResult  # object kit
    from plexhints.prefs_kit import Prefs  # prefs kit

# imports from Libraries\Shared
from typing import Optional, Union

try:
    # get the original Python builtins module
    python_builtins = inspect.getmodule(object)

    # get the Sandbox instance
    sandbox = inspect.stack()[1][0].f_locals["self"]

    # bypass RestrictedPython
    getattr(sandbox, "_core").loader.compile = lambda src, name, _=False: python_builtins.compile(src, name, "exec")

    # restore Python builtins
    sandbox.environment.update(python_builtins.vars(python_builtins))
except Exception as e:
    Log.Exception("Failed to bypass RestrictedPython: {}".format(e))

# local imports
from default_prefs import default_prefs
from constants import contributes_to, version
from plex_api_helper import plex_listener, start_queue_threads, update_plex_item
import migration_helper
from scheduled_tasks import setup_scheduling
from webapp import start_server

# variables
last_prefs = dict()


def copy_prefs():
    # type: () -> None
    """
    Copy the current preferences to the last preferences.

    This function is used to copy the current preferences to the last preferences. This is useful to determine if the
    preferences have changed.

    Examples
    --------
    >>> copy_prefs()
    """
    global last_prefs
    last_prefs = dict()

    for key in default_prefs:
        try:
            last_prefs[key] = Prefs[key]
        except KeyError:
            pass  # this was already logged


def ValidatePrefs():
    # type: () -> MessageContainer
    """
    Validate plug-in preferences.

    This function is called when the user modifies their preferences. The developer can check the newly provided values
    to ensure they are correct (e.g. attempting a login to validate a username and password), and optionally return a
    ``MessageContainer`` to display any error information to the user. See the archived Plex documentation
    `Predefined functions
    <https://web.archive.org/web/https://dev.plexapp.com/docs/channels/basics.html#predefined-functions>`_
    for more information.

    Returns
    -------
    MessageContainer
        Success or Error message dependeing on results of validation.

    Examples
    --------
    >>> ValidatePrefs()
    ...
    """
    global last_prefs

    # todo - validate username and password
    error_message = ''  # start with a blank error message

    for key in default_prefs:
        try:
            Prefs[key]
        except KeyError:
            Log.Critical("Setting '%s' missing from 'DefaultPrefs.json'" % key)
            error_message += "Setting '%s' missing from 'DefaultPrefs.json'<br/>" % key
        else:
            # test all types except 'str_' as string cannot fail
            if key.startswith('int_'):
                try:
                    int(Prefs[key])
                except ValueError:
                    Log.Error("Setting '%s' must be an integer; Value '%s'" % (key, Prefs[key]))
                    error_message += "Setting '%s' must be an integer; Value '%s'<br/>" % (key, Prefs[key])
            elif key.startswith('bool_'):
                if Prefs[key] is not True and Prefs[key] is not False:
                    Log.Error("Setting '%s' must be True or False; Value '%s'" % (key, Prefs[key]))
                    error_message += "Setting '%s' must be True or False; Value '%s'<br/>" % (key, Prefs[key])

            # special cases
            int_greater_than_zero = [
                'int_plexapi_plexapi_timeout',
                'int_plexapi_upload_threads'
            ]
            for test in int_greater_than_zero:
                if key == test and int(Prefs[key]) <= 0:
                    Log.Error("Setting '%s' must be greater than 0; Value '%s'" % (key, Prefs[key]))
                    error_message += "Setting '%s' must be greater than 0; Value '%s'<br/>" % (key, Prefs[key])

            # restart webserver if required
            requires_restart = [
                'str_webapp_http_host',
                'int_webapp_http_port',
                'bool_webapp_log_werkzeug_messages'
            ]

            if key in requires_restart:
                try:
                    if last_prefs[key] != Prefs[key]:
                        Log.Info('Changing this setting ({}) requires a Plex Media Server restart.'.format(key))
                except KeyError:
                    pass

    copy_prefs()  # since validate prefs runs on startup, this will have already run at least once

    # perform migrations
    migration_object = migration_helper.MigrationHelper()
    for key in default_prefs:
        migration_key_prefix = 'bool_migrate_'
        if key.startswith(migration_key_prefix):
            migration = key.replace(migration_key_prefix, '')
            migrated = migration_object.get_migration_status(key=migration)
            if Prefs[key] and not migrated:
                migration_object.perform_migration(key=migration)

    if error_message != '':
        return MessageContainer(header='Error', message=error_message)
    else:
        Log.Info("DefaultPrefs.json is valid")
        return MessageContainer(header='Success', message='Themerr-plex - Provided preference values are ok')


def Start():
    # type: () -> None
    """
    Start the plug-in.

    This function is called when the plug-in first starts. It can be used to perform extra initialisation tasks such as
    configuring the environment and setting default attributes. See the archived Plex documentation
    `Predefined functions
    <https://web.archive.org/web/https://dev.plexapp.com/docs/channels/basics.html#predefined-functions>`_
    for more information.

    Preferences are validated, then additional threads are started for the web server, queue, plex listener, and
    scheduled tasks.

    Examples
    --------
    >>> Start()
    ...
    """
    Log.Info('Themerr-plex, version: {}'.format(version))

    # validate prefs
    prefs_valid = ValidatePrefs()
    if prefs_valid.header == 'Error':
        Log.Warn('Themerr-plex plug-in preferences are not valid.')

    start_server()  # start the web server
    Log.Debug('web server started.')

    start_queue_threads()  # start queue threads
    Log.Debug('queue threads started.')

    if Prefs['bool_plex_movie_support'] or Prefs['bool_plex_series_support']:
        plex_listener()  # start watching plex
        Log.Debug('plex_listener started, watching for activity from new Plex Movie agent.')

    setup_scheduling()  # start scheduled tasks
    Log.Debug('scheduled tasks started.')

    Log.Debug('plug-in started.')


@handler(prefix='/applications/themerr-plex', name='Themerr-plex ({})'.format(version), thumb='icon-default.png')
def main():
    """
    Create the main plug-in ``handler``.

    This is responsible for displaying the plug-in in the plug-ins menu. Since we are using the ``@handler`` decorator,
    and since Plex removed menu's from plug-ins, this method does not need to perform any other function.
    """
    pass


class Themerr(object):
    """
    Class representing the Themerr-plex Agent.

    This class defines the metadata agent. See the archived Plex documentation
    `Defining an agent class
    <https://web.archive.org/web/https://dev.plexapp.com/docs/agents/basics.html#defining-an-agent-class>`_
    for more information.

    References
    ----------
    name : str
        A string defining the name of the agent for display in the GUI.
    languages : list
        A list of strings defining the languages supported by the agent. These values should be taken from the constants
        defined in the `Locale
        <https://web.archive.org/web/https://dev.plexapp.com/docs/api/localekit.html#module-Locale>`_
        API.
    primary_provider : py:class:`bool`
        A boolean value defining whether the agent is a primary metadata provider or not. Primary providers can be
        selected as the main source of metadata for a particular media type. If an agent is secondary
        (``primary_provider`` is set to ``False``) it will only be able to contribute to data provided by another
        primary agent.
    fallback_agent : Optional[str]
        A string containing the identifier of another agent to use as a fallback. If none of the matches returned by an
        agent are a close enough match to the given set of hints, this fallback agent will be called to attempt to find
        a better match.
    accepts_from : Optional[list]
        A list of strings containing the identifiers of agents that can contribute secondary data to primary data
        provided by this agent.
    contributes_to : Optional[list]
        A list of strings containing the identifiers of primary agents that the agent can contribute secondary data to.

    Methods
    -------
    search:
        Search for an item.
    update:
        Add or update metadata for an item.

    Examples
    --------
    >>> Themerr()
    ...
    """
    name = 'Themerr-plex'
    languages = [
        Locale.Language.English
    ]
    primary_provider = False
    fallback_agent = False
    accepts_from = []
    contributes_to = contributes_to

    def __init__(self, *args, **kwargs):
        super(Themerr, self).__init__(*args, **kwargs)
        self.agent_type = "movies" if isinstance(self, Agent.Movies) else "tv_shows"

    def search(self, results, media, lang, manual):
        # type: (SearchResult, Union[Media.Movie, Media.TV_Show], str, bool) -> Optional[SearchResult]
        """
        Search for an item.

        When the media server needs an agent to perform a search, it calls the agent’s ``search`` method. See the
        archived Plex documentation
        `Searching for results to provide matches for media
        <https://web.archive.org/web/https://dev.plexapp.com/docs/agents/search.html>`_
        for more information.

        Parameters
        ----------
        results : SearchResult
            An empty container that the developer should populate with potential matches.
        media : Union[Media.Movie, Media.TV_Show]
            An object containing hints to be used when performing the search.
        lang : str
            A string identifying the user’s currently selected language. This will be one of the constants added to the
            agent’s ``languages`` attribute.
        manual : py:class:`bool`
            A boolean value identifying whether the search was issued automatically during scanning, or manually by the
            user (in order to fix an incorrect match).

        Returns
        -------
        Optional[SearchResult]
            The search result object, if the search was successful.

        Examples
        --------
        >>> Themerr().search(results=..., media=..., lang='en', manual=True)
        ...
        """
        Log.Debug('Searching with arguments: {results=%s, media=%s, lang=%s, manual=%s' %
                  (results, media, lang, manual))

        if media.primary_metadata is None or media.primary_agent is None:
            Log.Error('Search is being called in a primary agent.')
            return

        Log.Debug('Primary agent: %s' % media.primary_agent)
        Log.Debug('media.primary_metadata.id: %s' % media.primary_metadata.id)

        # the media_id will be used to create the url path, replacing `-` with `/`
        if media.primary_agent == 'dev.lizardbyte.retroarcher-plex':
            media_id = 'games-%s' % re.search(r'((igdb)-(\d+))', media.primary_metadata.id).group(1)
        else:
            media_id = '{}-{}-{}'.format(
                self.agent_type,
                media.primary_agent.rsplit('.', 1)[-1],
                media.primary_metadata.id
            )
            # e.g. = 'movies-imdb-tt0113189'
            # e.g. = 'movies-themoviedb-710'

        results.Append(MetadataSearchResult(
            id=media_id,
            name=media.primary_metadata.title,
            year=getattr(media.primary_metadata, 'year', None),  # TV Shows don't have a year attribute
            score=100,
            lang=lang,  # no lang to get from db
            thumb=None  # no point in adding thumb since plex won't show it anywhere
        ))

        # sort the results first by year, then by score
        results.Sort(attr='year')
        results.Sort(attr='score', descending=True)
        return results

    @staticmethod
    def update(metadata, media, lang, force):
        # type: (MetadataModel, Union[Media.Movie, Media.TV_Show], str, bool) -> MetadataModel
        """
        Update metadata for an item.

        Once an item has been successfully matched, it is added to the update queue. As the framework processes queued
        items, it calls the ``update`` method of the relevant agents. See the archived Plex documentation
        `Adding metadata to media
        <https://web.archive.org/web/https://dev.plexapp.com/docs/agents/update.html>`_
        for more information.

        Parameters
        ----------
        metadata : MetadataModel
            A pre-initialized metadata object if this is the first time the item is being updated, or the existing
            metadata object if the item is being refreshed.
        media : Union[Media.Movie, Media.TV_Show]
            An object containing information about the media hierarchy in the database.
        lang : str
            A string identifying which language should be used for the metadata. This will be one of the constants
            defined in the agent’s ``languages`` attribute.
        force : py:class:`bool`
            A boolean value identifying whether the user forced a full refresh of the metadata. If this argument is
            ``True``, all metadata should be refreshed, regardless of whether it has been populated previously.

        Returns
        -------
        MetadataModel
            The metadata object.

        Examples
        --------
        >>> Themerr().update(metadata=..., media=..., lang='en', force=True)
        ...
        """
        Log.Debug('Updating with arguments: {metadata=%s, media=%s, lang=%s, force=%s' %
                  (metadata, media, lang, force))

        rating_key = int(media.id)  # rating key of plex item
        update_plex_item(rating_key=rating_key)

        return metadata


class ThemerrMovies(Themerr, Agent.Movies):
    agent_type_verbose = "Movies"


class ThemerrTvShows(Themerr, Agent.TV_Shows):
    agent_type_verbose = "TV"
