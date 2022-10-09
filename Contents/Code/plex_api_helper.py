# -*- coding: utf-8 -*-

# plex debugging
try:
    import plexhints  # noqa: F401
except ImportError:
    pass
else:  # the code is running outside of Plex
    from plexhints.log_kit import Log
    from plexhints.prefs_kit import Prefs

# imports from Libraries\Shared
import requests
from typing import Optional
import urllib3
import plexapi
from plexapi.server import PlexServer


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
    plexapi.TIMEOUT = int(Prefs['int_upload_timeout'])

    plex_url = Prefs['url_plex_server']
    Log.Debug('Plex url: %s' % plex_url)

    plex_token = Prefs['str_plex_token']

    if not plex_token:
        Log.Error('Plex token not set in agent settings, cannot proceed.')
        return False

    sess = requests.Session()
    sess.verify = False  # Ignore verifying the SSL certificate
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # Disable the insecure request warning

    # create the plex server object
    plex = PlexServer(baseurl=plex_url, token=plex_token, session=sess)

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
