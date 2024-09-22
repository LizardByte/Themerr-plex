# standard imports
import json
import os
import tempfile
from typing import Optional

# lib imports
import yt_dlp

# local imports
from common import config
from common import definitions
from common import logger

log = logger.get_logger(name=__name__)


def ns_bool(value: bool) -> str:
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


def process_youtube(url: str) -> Optional[str]:
    """
    Process URL using `yt_dlp`

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

    cookie_jar_file = tempfile.NamedTemporaryFile(
        dir=os.path.join(definitions.Paths.CONFIG_DIR, 'cookies'),
        delete=False,
    )
    cookie_jar_file.write('# Netscape HTTP Cookie File\n')

    youtube_dl_params = dict(
        cookiefile=cookie_jar_file.name,
        logger=log,
        socket_timeout=10,
        youtube_include_dash_manifest=False,
    )

    if config.CONFIG['Themerr']['STR_YOUTUBE_COOKIES']:
        try:
            cookies = json.loads(config.CONFIG['Themerr']['STR_YOUTUBE_COOKIES'])
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
                cookie_jar_file.write(f'{'\t'.join(values)}\n')
        except Exception as e:
            log.exception(f'Failed to write YouTube cookies to file, will try anyway. Error: {e}')

    cookie_jar_file.flush()
    cookie_jar_file.close()

    try:
        ydl = yt_dlp.YoutubeDL(params=youtube_dl_params)

        with ydl:
            try:
                result = ydl.extract_info(
                    url=url,
                    download=False  # We just want to extract the info
                )
            except Exception as exc:
                if isinstance(exc, yt_dlp.utils.ExtractorError) and exc.expected:
                    log.info(f'yt-dlp returned YT error while downloading {url}: {exc}')
                else:
                    log.exception(f'yt-dlp returned an unexpected error while downloading {url}: {exc}')
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
                        log.debug(f'Unknown codec: {fmt['acodec']}')
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

        if audio_url and config.CONFIG['Themerr']['BOOL_PREFER_MP4A_CODEC']:  # mp4a codec is preferred
            if selected['mp4a']['audio_url']:  # mp4a codec is available
                audio_url = selected['mp4a']['audio_url']
            elif selected['opus']['audio_url']:  # fallback to opus :(
                audio_url = selected['opus']['audio_url']

        return audio_url  # return None or url found
    finally:
        try:
            os.remove(cookie_jar_file.name)
        except Exception as e:
            log.exception(f'Failed to delete cookie jar file: {e}')
