# -*- coding: utf-8 -*-

# standard imports
import logging
import json
import os
import re
import tempfile
import time
import urlparse

# plex debugging
try:
    import plexhints  # noqa: F401
except ImportError:
    pass
else:  # the code is running outside of Plex
    from plexhints.log_kit import Log  # log kit
    from plexhints.prefs_kit import Prefs  # prefs kit

# imports from Libraries\Shared
import requests
from typing import Optional
import youtube_dl

# local imports
from constants import plugin_identifier, plugin_support_data_directory

# get the plugin logger
plugin_logger = logging.getLogger(plugin_identifier)


def build_fallback_playback_url(playback_url):
    # type: (str) -> Optional[str]
    """
    Build a fallback URL for a YouTube video.

    Parameters
    ----------
    playback_url : str
        The playback URL of the YouTube audio/video format.

    Returns
    -------
    Optional[str]
        The fallback URL of the playback URL.
    """
    query = youtube_dl.utils.parse_qs(url=playback_url)
    mn = query.get('mn', [''])[0]
    fvip = query.get('fvip', [''])[0]

    mn = youtube_dl.utils.str_or_none(mn, '').split(',')
    if len(mn) > 1 and mn[1] and fvip:
        fmt_url_parsed = urlparse.urlparse(playback_url)
        new_netloc = re.sub(
            r'\d+', fvip, fmt_url_parsed.netloc.split('---')[0]) + '---' + mn[1] + '.googlevideo.com'

        return youtube_dl.utils.update_url_query(
            url=fmt_url_parsed._replace(netloc=new_netloc).geturl(),
            query={'fallback_count': '1'},
        )


def ns_bool(value):
    # type: (bool) -> str
    """
    Format a boolean value for a Netscape cookie jar file.

    Parameters
    ----------
    value : py:class:`bool`
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
        cookiefile=cookie_jar_file.name if Prefs['str_youtube_cookies'] else None,
        logger=plugin_logger,
        noplaylist=True,
        socket_timeout=10,
        youtube_include_dash_manifest=False,
    )

    if Prefs['str_youtube_cookies']:
        try:
            cookies = json.loads(Prefs['str_youtube_cookies'])
            for cookie in cookies:
                include_subdomain = cookie['domain'].startswith('.')
                expiry = int(cookie.get('expiry', 0))
                values = [
                    cookie['domain'],
                    ns_bool(include_subdomain),
                    cookie['path'],
                    ns_bool(cookie['secure']),
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

        audio_url = None

        count = 0
        while count <= max(0, int(Prefs['int_youtube_retries_max'])):
            sleep_time = 2 ** count
            time.sleep(sleep_time)
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
                    count += 1
                    continue

                # If a playlist was provided, select the first video
                video_data = result['entries'][0] if 'entries' in result else result if result else {}

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

            # loop through formats, select the largest audio size for better quality
            for fmt in video_data.get('formats', []):
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

            if 0 < selected['opus']['size'] > selected['mp4a']['size']:
                audio_url = selected['opus']['audio_url']
            elif 0 < selected['mp4a']['size'] > selected['opus']['size']:
                audio_url = selected['mp4a']['audio_url']

            if audio_url and Prefs['bool_prefer_mp4a_codec']:  # mp4a codec is preferred
                if selected['mp4a']['audio_url']:  # mp4a codec is available
                    audio_url = selected['mp4a']['audio_url']
                elif selected['opus']['audio_url']:  # fallback to opus :(
                    audio_url = selected['opus']['audio_url']

            if audio_url:
                validate = requests.get(url=audio_url, stream=True)
                if validate.status_code == 200:
                    return audio_url
                else:
                    Log.Warn('Failed to validate audio URL for video {}'.format(url))

                    # build a fallback URL
                    fallback_url = build_fallback_playback_url(playback_url=audio_url)
                    if fallback_url:
                        audio_url = fallback_url
                        Log.Warn('Trying fallback URL for video {}'.format(url))
                        validate = requests.get(url=audio_url, stream=True)
                        if validate.status_code == 200:
                            return audio_url
                        else:
                            Log.Warn('Failed to validate fallback URL for video {}'.format(url))
                            audio_url = None
                    else:
                        Log.Warn('Failed to build fallback URL for video {}'.format(url))
                        audio_url = None

                    count += 1
                    continue

            return audio_url  # return None or url found
    finally:
        try:
            os.remove(cookie_jar_file.name)
        except Exception as e:
            Log.Exception('Failed to delete cookie jar file: {}'.format(e))
