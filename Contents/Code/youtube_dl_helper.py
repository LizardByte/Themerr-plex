# -*- coding: utf-8 -*-

# standard imports
import logging
import json
import os
import tempfile

# plex debugging
try:
    import plexhints  # noqa: F401
except ImportError:
    pass
else:  # the code is running outside of Plex
    from plexhints.log_kit import Log  # log kit
    from plexhints.prefs_kit import Prefs  # prefs kit

# imports from Libraries\Shared
from typing import Optional
import youtube_dl

# local imports
from constants import plugin_identifier, plugin_support_data_directory
from selenium_helper import get_yt_cookies

# get the plugin logger
plugin_logger = logging.getLogger(plugin_identifier)


def nsbool(value):
    # type: (bool) -> str
    """
    Format a boolean value for a Netscape cookie jar file.

    Parameters
    ----------
    value : bool
        The boolean value to format.

    Returns
    -------
    str
        'TRUE' or 'FALSE'.
    """
    return 'TRUE' if value else 'FALSE'


def process_youtube(url):
    # type: (str) -> Optional[str]
    """
    Process URL using `youtube_dl`

    Parameters
    ----------
    url : str
       The URL of the YouTube video.

    Returns
    -------
    Optional[str]
       The URL of the audio object.

    Examples
    --------
    >>> process_youtube(url='https://www.youtube.com/watch?v=dQw4w9WgXcQ')
    ...
    """

    cookie_jar_file = tempfile.NamedTemporaryFile(dir=plugin_support_data_directory, delete=False)
    cookie_jar_file.write('# Netscape HTTP Cookie File\n')

    youtube_dl_params = dict(
        cookiefile=cookie_jar_file.name,
        logger=plugin_logger,
        socket_timeout=10,
        youtube_include_dash_manifest=False,
    )

    if Prefs['bool_youtube_cookies']:
        try:
            cookies = get_yt_cookies()
            for cookie in cookies:
                include_subdomain = cookie['domain'].startswith('.')
                expiry = int(cookie.get('expiry', 0))
                values = [
                    cookie['domain'],
                    nsbool(include_subdomain),
                    cookie['path'],
                    nsbool(cookie['secure']),
                    str(expiry),
                    cookie['name'],
                    cookie['value']
                ]
                cookie_jar_file.write('{}\n'.format('\t'.join(values)))
        except Exception as e:
            Log.Exception('Failed to write YouTube cookies to file, will try anyway. Error: {}'.format(e))

    cookie_jar_file.flush()
    cookie_jar_file.close()

    try:
        ydl = youtube_dl.YoutubeDL(params=youtube_dl_params)

        with ydl:
            try:
                result = ydl.extract_info(
                    url=url,
                    download=False  # We just want to extract the info
                )
            except Exception as exc:
                if isinstance(exc, youtube_dl.utils.ExtractorError) and exc.expected:
                    Log.Info('YDL returned YT error while downloading {}: {}'.format(url, exc))
                else:
                    Log.Exception('YDL returned an unexpected error while downloading {}: {}'.format(url, exc))
                return None

            if 'entries' in result:
                # Can be a playlist or a list of videos
                video_data = result['entries'][0]
            else:
                # Just a video
                video_data = result

        selected = {
            'opus': {
                'size': 0,
                'audio_url': None
            },
            'mp4a': {
                'size': 0,
                'audio_url': None
            },
        }
        if video_data:
            for fmt in video_data['formats']:  # loop through formats, select largest audio size for better quality
                if 'audio only' in fmt['format']:
                    if 'opus' == fmt['acodec']:
                        temp_codec = 'opus'
                    elif 'mp4a' == fmt['acodec'].split('.')[0]:
                        temp_codec = 'mp4a'
                    else:
                        Log.Debug('Unknown codec: %s' % fmt['acodec'])
                        continue  # unknown codec
                    filesize = int(fmt['filesize'])
                    if filesize > selected[temp_codec]['size']:
                        selected[temp_codec]['size'] = filesize
                        selected[temp_codec]['audio_url'] = fmt['url']

        audio_url = None

        if 0 < selected['opus']['size'] > selected['mp4a']['size']:
            audio_url = selected['opus']['audio_url']
        elif 0 < selected['mp4a']['size'] > selected['opus']['size']:
            audio_url = selected['mp4a']['audio_url']

        if audio_url and Prefs['bool_prefer_mp4a_codec']:  # mp4a codec is preferred
            if selected['mp4a']['audio_url']:  # mp4a codec is available
                audio_url = selected['mp4a']['audio_url']
            elif selected['opus']['audio_url']:  # fallback to opus :(
                audio_url = selected['opus']['audio_url']

        return audio_url  # return None or url found
    finally:
        try:
            os.remove(cookie_jar_file.name)
        except Exception as e:
            Log.Exception('Failed to delete cookie jar file: {}'.format(e))
