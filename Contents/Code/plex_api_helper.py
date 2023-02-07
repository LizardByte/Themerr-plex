# -*- coding: utf-8 -*-

# standard imports
import os
import sys
import time
import threading

# plex debugging
try:
    import plexhints  # noqa: F401
except ImportError:
    pass
else:  # the code is running outside of Plex
    from plexhints.log_kit import Log  # log kit
    from plexhints.prefs_kit import Prefs  # prefs kit

# imports from Libraries\Shared
from future.moves import queue
import requests
from typing import Optional
import urllib3
from urllib3.exceptions import InsecureRequestWarning
from plexapi.alert import AlertListener
from plexapi.exceptions import BadRequest
import plexapi.server
from plexapi.utils import reverseSearchType

# local imports
if sys.version_info.major < 3:
    from helpers import get_json, guid_map, issue_url_movies
    from youtube_dl_helper import process_youtube
else:
    from .helpers import get_json, guid_map, issue_url_movies
    from .youtube_dl_helper import process_youtube

plex = None

# list currently processing items to avoid processing again
q = queue.Queue()
processing_completed = []


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
    # type: (int, Optional[list], Optional[list]) -> bool
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

    Returns
    -------
    bool
        True if the themes were added successfully, False otherwise.

    Examples
    --------
    >>> add_themes(theme_list=[...], rating_key=...)
    """
    uploaded = False

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
                    uploaded = upload_theme(plex_item=plex_item, filepath=theme_file)
            if theme_urls:
                for theme_url in theme_urls:
                    Log.Info('Attempting to upload theme file: %s' % theme_url)
                    uploaded = upload_theme(plex_item=plex_item, url=theme_url)
    else:
        Log.Info('No theme songs provided for rating key: %s' % rating_key)

    return uploaded


def upload_theme(plex_item, filepath=None, url=None):
    # type: (any, Optional[str], Optional[str]) -> bool
    """
    Upload a theme to the specified item.

    Uploads a theme to the item specified by the ``plex_item``.

    Parameters
    ----------
    plex_item : any
        The item to upload the theme to.
    filepath : Optional[str]
        The path to the theme song.
    url : Optional[str]
        The url to the theme song.

    Returns
    -------
    bool
        True if the theme was uploaded successfully, False otherwise.

    Examples
    --------
    >>> upload_theme(plex_item=..., url=...)
    ...
    """
    count = 0
    while count <= int(Prefs['int_plexapi_upload_retries_max']):
        try:
            if filepath:
                plex_item.uploadTheme(filepath=filepath)
            elif url:
                plex_item.uploadTheme(url=url)
        except BadRequest as e:
            sleep_time = 2**count
            Log.Error('%s: Error uploading theme: %s' % (plex_item.ratingKey, e))
            Log.Error('%s: Trying again in : %s' % (plex_item.ratingKey, sleep_time))
            time.sleep(sleep_time)
            count += 1
        else:
            return True
    return False


def get_plex_item(rating_key):
    # type: (int) -> any
    """
    Get any item from the Plex Server.

    This function is used to get an item from the Plex Server. It can then be used to get the metadata for the item.

    Parameters
    ----------
    rating_key : int
        The ``rating_key`` of the item to upload a theme for.

    Returns
    -------
    any
        The item from the Plex Server.

    Examples
    --------
    >>> get_plex_item(rating_key=1)
    ...
    """
    global plex, processing_completed
    if not plex:
        plex = setup_plexapi()
    plex_item = plex.fetchItem(ekey=rating_key)

    return plex_item


def process_queue():
    # type: () -> None
    """
    Add items to the queue.

    This is an endless loop to add items to the queue.

    Examples
    --------
    >>> t = threading.Thread(target=process_queue, daemon=True)
    ...
    """
    while True:
        rating_key = q.get()  # get the rating_key from the queue
        update_plex_movie_item(rating_key=rating_key)  # process that rating_key
        q.task_done()  # tells the queue that we are done with this item


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
    # create multiple threads for processing themes faster
    # minimum value of 1
    for t in range(max(1, int(Prefs['int_plexapi_upload_threads']))):
        try:
            # for each thread, start it
            t = threading.Thread(target=process_queue)
            # when we set daemon to true, that thread will end when the main thread ends
            t.daemon = True
            # start the daemon thread
            t.start()
        except RuntimeError as e:
            Log.Error('RuntimeError encountered: %s' % e)
            break

    global plex
    if not plex:
        plex = setup_plexapi()
    listener = AlertListener(server=plex, callback=plex_listener_handler, callbackError=Log.Error)
    listener.start()


def plex_listener_handler(data):
    # type: (dict) -> None
    """
    Process events from ``plex_listener()``.

    Check if we need to add an item to the queue or remove it from the ``processing_completed`` list.

    Parameters
    ----------
    data : dict
        Data received from the Plex server.

    Examples
    --------
    >>> plex_listener_handler(data={'type': 'timeline'})
    ...
    """
    global processing_completed
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

                rating_key = int(entry['itemID'])

                # check if entry has already processed to avoid endless looping
                if rating_key in processing_completed:
                    processing_completed.remove(int(entry['itemID']))
                    Log.Debug('Finished uploading theme: {title=%s, rating_key=%s}' %
                              (entry['title'], entry['itemID']))
                    return
                elif rating_key not in q.queue:
                    q.put(item=rating_key)


def update_plex_movie_item(rating_key):
    # type: (int) -> None
    """
    Upload theme songs to the Plex Media Server.

    Add themes to the server. Once finished, add the ``rating_key`` to the ``processing_completed`` list.

    Parameters
    ----------
    rating_key : int
        The ``rating_key`` of the item to upload a theme for.

    Examples
    --------
    >>> update_plex_movie_item(rating_key=1)
    ...
    """
    global plex, processing_completed
    if not plex:
        plex = setup_plexapi()
    plex_item = plex.fetchItem(ekey=rating_key)

    themerr_db_logs = []

    # guids does not appear to exist for legacy agents or plugins
    # therefore, we don't need to filter those out
    for guid in plex_item.guids:
        split_guid = guid.id.split('://')
        database = guid_map[split_guid[0]]
        database_id = split_guid[1]

        Log.Debug('%s: Attempting update for: {title=%s, rating_key=%s, database=%s, database_id=%s}' %
                  (rating_key, plex_item.title, plex_item.ratingKey, database, database_id))

        url = 'https://app.lizardbyte.dev/ThemerrDB/movies/%s/%s.json' % (database, database_id)

        try:
            data = get_json(url=url)
        except Exception:
            themerr_db_logs.append('%s: Could not retrieve data from ThemerrDB using %s' % (rating_key, database))
            if database == 'themoviedb':
                issue_title = '%s (%s)' % (plex_item.title, plex_item.year)
                issue_url = issue_url_movies % (issue_title, database_id)
                themerr_db_logs.insert(
                    0,
                    '%s: Theme song missing in ThemerrDB. Add it here -> "%s"' % (rating_key, issue_url)
                )
        else:
            try:
                yt_video_url = data['youtube_theme_url']
            except KeyError:
                Log.Info('%s: No theme song found for %s (%s)' % (rating_key, plex_item.title, plex_item.year))
                return
            else:
                theme_url = process_youtube(url=yt_video_url)

                if theme_url:
                    theme_added = add_themes(rating_key=plex_item.ratingKey, theme_urls=[theme_url])

                    # add the item to processing_completed list
                    if theme_added:
                        processing_completed.append(rating_key)

                        # theme found and uploaded using this database, so return
                        return

    # could not upload theme using any database, so log the errors
    for log in themerr_db_logs:
        Log.Error(log)
