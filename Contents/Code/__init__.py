# -*- coding: utf-8 -*-

# standard imports
import re
import sys

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
    from plexhints.model_kit import Movie  # model kit
    from plexhints.object_kit import MessageContainer, MetadataSearchResult, SearchResult  # object kit
    from plexhints.parse_kit import JSON  # parse kit
    from plexhints.prefs_kit import Prefs  # prefs kit

# imports from Libraries\Shared
from typing import Optional

# local imports
if sys.version_info.major < 3:
    from default_prefs import default_prefs
    from plex_api_helper import add_themes, plex_listener
    from youtube_dl_helper import process_youtube
else:
    from .default_prefs import default_prefs
    from .plex_api_helper import add_themes, plex_listener
    from .youtube_dl_helper import process_youtube


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

    if error_message != '':
        return MessageContainer(header='Error', message=error_message)
    else:
        Log.Info("DefaultPrefs.json is valid")
        return MessageContainer(header='Success', message='RetroArcher - Provided preference values are ok')


def Start():
    # type: () -> None
    """
    Start the plug-in.

    This function is called when the plug-in first starts. It can be used to perform extra initialisation tasks such as
    configuring the environment and setting default attributes. See the archived Plex documentation
    `Predefined functions
    <https://web.archive.org/web/https://dev.plexapp.com/docs/channels/basics.html#predefined-functions>`_
    for more information.

    First preferences are validated using the ``ValidatePrefs()`` method. Then the ``plex_api_helper.plex_listener()``
    method is started to handle updating theme songs for the new Plex Movie agent.

    Examples
    --------
    >>> Start()
    ...
    """
    # validate prefs
    prefs_valid = ValidatePrefs()
    if prefs_valid.header == 'Error':
        Log.Warn('Themerr-plex plug-in preferences are not valid.')

    Log.Debug('Themerr-plex plug-in started.')

    # start watching plex
    plex_listener()
    Log.Debug('plex_listener started, watching for activity from new Plex Movie agent.')


@handler(prefix='/music/themerr-plex', name='Themerr-plex', thumb='attribution.png')
def main():
    """
    Create the main plug-in ``handler``.

    This is responsible for displaying the plug-in in the plug-ins menu. Since we are using the ``@handler`` decorator,
    and since Plex removed menu's from plug-ins, this method does not need to perform any other function.
    """
    pass


class Themerr(Agent.Movies):
    """
    Class representing the Themerr-plex Movie Agent.

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
    primary_provider : bool
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
    contributes_to = [
        'com.plexapp.agents.imdb',
        'com.plexapp.agents.themoviedb',
        # 'com.plexapp.agents.thetvdb',  # not available as movie agent
        'dev.lizardbyte.retroarcher-plex'
    ]

    @staticmethod
    def search(results, media, lang, manual):
        # type: (SearchResult, Media.Movie, str, bool) -> Optional[SearchResult]
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
        media : Media.Movie
            An object containing hints to be used when performing the search.
        lang : str
            A string identifying the user’s currently selected language. This will be one of the constants added to the
            agent’s ``languages`` attribute.
        manual : bool
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
        if media.primary_metadata == 'dev.lizardbyte.retroarcher-plex':
            media_id = 'games-%s' % re.search(r'((igdb)-(\d+))', media.primary_metadata.id).group(1)
        else:
            media_id = 'movies-%s-%s' % (media.primary_agent.rsplit('.', 1)[-1], media.primary_metadata.id)
            # e.g. = 'movies-imdb-tt0113189'
            # e.g. = 'movies-themoviedb-710'

        results.Append(MetadataSearchResult(
            id=media_id,
            name=media.primary_metadata.title,
            year=media.primary_metadata.year,
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
        # type: (Movie, Media.Movie, str, bool) -> Optional[Movie]
        """
        Update metadata for an item.

        Once an item has been successfully matched, it is added to the update queue. As the framework processes queued
        items, it calls the ``update`` method of the relevant agents. See the archived Plex documentation
        `Adding metadata to media
        <https://web.archive.org/web/https://dev.plexapp.com/docs/agents/update.html>`_
        for more information.

        Parameters
        ----------
        metadata : object
            A pre-initialized metadata object if this is the first time the item is being updated, or the existing
            metadata object if the item is being refreshed.
        media : object
            An object containing information about the media hierarchy in the database.
        lang : str
            A string identifying which language should be used for the metadata. This will be one of the constants
            defined in the agent’s ``languages`` attribute.
        force : bool
            A boolean value identifying whether the user forced a full refresh of the metadata. If this argument is
            ``True``, all metadata should be refreshed, regardless of whether it has been populated previously.

        Examples
        --------
        >>> Themerr().update(metadata=..., media=..., lang='en', force=True)
        ...
        """
        Log.Debug('Updating with arguments: {metadata=%s, media=%s, lang=%s, force=%s' %
                  (metadata, media, lang, force))

        rating_key = int(media.id)  # rating key of plex item
        Log.Info('Rating key: %s' % rating_key)

        Log.Info('metadata.id: %s' % metadata.id)
        url = 'https://app.lizardbyte.dev/ThemerrDB/%s.json' % metadata.id.replace('-', '/')

        data = JSON.ObjectFromURL(url=url, errors='ignore')

        try:
            yt_video_url = data['youtube_theme_url']
        except KeyError:
            Log.Info('No theme song found for %s (%s)' % (metadata.title, metadata.year))
            return
        else:
            theme_url = process_youtube(url=yt_video_url)

            if theme_url:
                add_themes(rating_key=rating_key, theme_urls=[theme_url])

        return metadata
