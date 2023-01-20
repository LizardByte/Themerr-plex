# -*- coding: utf-8 -*-

# standard imports
import os
import sys

# plex debugging
try:
    import plexhints  # noqa: F401
except ImportError:
    pass
else:  # the code is running outside of Plex
    from plexhints.log_kit import Log  # log kit
    from plexhints.parse_kit import JSON  # parse kit
    from plexhints.prefs_kit import Prefs  # prefs kit

# imports from Libraries\Shared
import requests
from typing import Optional
import urllib3
from urllib3.exceptions import InsecureRequestWarning
from plexapi.alert import AlertListener
import plexapi.server
from plexapi.utils import reverseSearchType

# local imports
if sys.version_info.major < 3:
    from helpers import guid_map
    from youtube_dl_helper import process_youtube
else:
    from .helpers import guid_map
    from .youtube_dl_helper import process_youtube

plex = None

# list currently processing items to avoid processing again
processing = []


def setup_plexapi():
    """
    Create the Plex server object.

    It is required to use PlexAPI in order to add theme music to movies, as the built-in methods for metadata agents
    do not work for movies. This method creates the server object.

    Returns
    -------
    PlexServer
        The PlexServer object.

    Examples
    --------
    >>> setup_plexapi()
    ...
    """
    global plex
    if not plex:
        plex_url = 'http://localhost:32400'
        plex_token = os.environ.get('PLEXTOKEN')

        if not plex_token:
            Log.Error('Plex token not found in environment, cannot proceed.')
            return False

        sess = requests.Session()
        sess.verify = False  # Ignore verifying the SSL certificate
        urllib3.disable_warnings(InsecureRequestWarning)  # Disable the insecure request warning

        # create the plex server object
        plexapi.server.TIMEOUT = int(Prefs['int_plexapi_plexapi_timeout'])
        plex = plexapi.server.PlexServer(baseurl=plex_url, token=plex_token, session=sess)

    return plex


def add_themes(rating_key, theme_files=None, theme_urls=None):
    # type: (int, Optional[list], Optional[list]) -> None
    """
    Apply themes to the specified item.

    Adds theme songs to the item specified by the ``rating_key``.

    Parameters
    ----------
    rating_key : str
        The key corresponding to the item that the themes will be added to.
    theme_files : Optional[list]
        A list of paths to theme songs.
    theme_urls : Optional[list]
        A list of urls to theme songs.

    Examples
    --------
    >>> add_themes(theme_list=[...], rating_key=...)
    """
    if theme_files or theme_urls:
        global plex
        if not plex:
            plex = setup_plexapi()

        Log.Info('Plexapi working with item with rating key: %s' % rating_key)

        if plex:
            plex_item = plex.fetchItem(ekey=int(rating_key))  # must be an int or weird things happen

            if theme_files:
                for theme_file in theme_files:
                    Log.Info('Attempting to upload theme file: %s' % theme_file)
                    plex_item.uploadTheme(filepath=theme_file)
            if theme_urls:
                for theme_url in theme_urls:
                    Log.Info('Attempting to upload theme file: %s' % theme_url)
                    plex_item.uploadTheme(url=theme_url)
    else:
        Log.Info('No theme songs provided for rating key: %s' % rating_key)


def plex_listener():
    # type: () -> None
    """
    Listen for events from Plex server.

    Send events to ``plex_listener_handler`` and errors to ``Log.Error``.

    Examples
    --------
    >>> plex_listener()
    ...
    """
    global plex
    if not plex:
        plex = setup_plexapi()
    listener = AlertListener(server=plex, callback=plex_listener_handler, callbackError=Log.Error)
    listener.run()


def plex_listener_handler(data):
    # type: (dict) -> None
    """
    Process events from ``plex_listener()``.

    Check if ``data`` is for an event that indicates metadata update has finished for a movie item, and process further
    as required.

    Parameters
    ----------
    data : dict
        Data received from the Plex server.

    Examples
    --------
    >>> plex_listener_handler(data={'type': 'timeline'})
    ...
    """
    global plex, processing
    if not plex:
        plex = setup_plexapi()
    # Log.Debug(data)
    if data['type'] == 'timeline':
        for entry in data['TimelineEntry']:
            # known state values:
            # https://python-plexapi.readthedocs.io/en/latest/modules/alert.html#module-plexapi.alert

            # known search types:
            # https://github.com/pkkid/python-plexapi/blob/8b3235445f6b3051c39ff6d6fc5d49f4e674d576/plexapi/utils.py#L35-L55
            if (reverseSearchType(libtype=entry['type']) == 'movie'
                    and entry['state'] == 5
                    and entry['identifier'] == 'com.plexapp.plugins.library'):
                # todo - add themes for collections
                # identifier always appears to be `com.plexapp.plugins.library` for updating library metadata
                # entry['title'] = movie title
                # entry['itemID'] = rating key

                # check if entry is already processing to avoid endless looping
                if int(entry['itemID']) in processing:
                    processing.remove(int(entry['itemID']))
                    Log.Debug('Finished uploading theme: {title=%s, rating_key=%s}' %
                              (entry['title'], entry['itemID']))
                    return

                plex_item = plex.fetchItem(ekey=int(entry['itemID']))  # must be an int or weird things happen

                # guids does not appear to exist for legacy agents or plugins
                # therefore, we don't need to filter those out
                for guid in plex_item.guids:
                    split_guid = guid.id.split('://')
                    database = guid_map[split_guid[0]]
                    database_id = split_guid[1]

                    Log.Debug('Attempting update for: {title=%s, rating_key=%s, database=%s, database_id=%s}' %
                              (plex_item.title, plex_item.ratingKey, database, database_id))

                    url = 'https://app.lizardbyte.dev/ThemerrDB/movies/%s/%s.json' % (database, database_id)

                    data = JSON.ObjectFromURL(url=url, errors='ignore')

                    try:
                        yt_video_url = data['youtube_theme_url']
                    except KeyError:
                        Log.Info('No theme song found for %s (%s)' % (plex_item.title, plex_item.year))
                        return
                    else:
                        theme_url = process_youtube(url=yt_video_url)

                        if theme_url:
                            processing.append(plex_item.ratingKey)
                            add_themes(rating_key=plex_item.ratingKey, theme_urls=[theme_url])

                            # theme found and uploaded using this database, so return
                            return
