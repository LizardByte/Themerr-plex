"""Resolve a YouTube video's audio stream with yt-dlp."""

# standard imports
import json
import os
import sys
import tempfile
from typing import Optional, TextIO

# lib imports
import yt_dlp

# local imports
from common import config
from common import definitions
from common import logger

log = logger.get_logger(name=__name__)


def ns_bool(value: bool) -> str:
    """
    Format a boolean for a Netscape cookie file.

    Parameters
    ----------
    value : bool
        Boolean value to format.

    Returns
    -------
    str
        ``TRUE`` or ``FALSE``.
    """
    return 'TRUE' if value else 'FALSE'


def _write_cookies(cookie_file: TextIO, raw_cookies: str) -> None:
    """Write configured cookies in Netscape format.

    Parameters
    ----------
    cookie_file : TextIO
        Open temporary cookie file.
    raw_cookies : str
        JSON encoded browser cookies.
    """
    cookie_file.write('# Netscape HTTP Cookie File\n')
    if not raw_cookies:
        return
    try:
        for cookie in json.loads(raw_cookies):
            values = [
                cookie['domain'],
                ns_bool(cookie['domain'].startswith('.')),
                cookie['path'],
                ns_bool(cookie['secure']),
                str(int(cookie.get('expiry', 0))),
                cookie['name'],
                cookie['value'],
            ]
            cookie_file.write('\t'.join(values) + '\n')
    except (ValueError, KeyError, TypeError) as exc:
        log.warning('Failed to write YouTube cookies; continuing without them: %s', exc)


def _extract_video(url: str, params: dict) -> Optional[dict]:
    """Extract a video or the first available playlist entry.

    Parameters
    ----------
    url : str
        Video or playlist URL.
    params : dict
        yt-dlp options.

    Returns
    -------
    dict or None
        Extracted video data when available.
    """
    with yt_dlp.YoutubeDL(params=params) as ydl:
        try:
            result = ydl.extract_info(url=url, download=False)
        except yt_dlp.utils.ExtractorError as exc:
            if exc.expected:
                log.info('yt-dlp could not extract %s: %s', url, exc)
            else:
                log.exception('yt-dlp failed to extract %s', url)
            return None
        except Exception:
            log.exception('yt-dlp failed to extract %s', url)
            return None

    if not result:
        return None
    return next((entry for entry in result['entries'] if entry), None) if 'entries' in result else result


def _select_audio(video: dict) -> Optional[str]:
    """Choose the largest supported audio stream from extracted formats.

    Parameters
    ----------
    video : dict
        Extracted video data.

    Returns
    -------
    str or None
        Selected stream URL.
    """
    selected = {}
    for fmt in video.get('formats', []):
        if fmt.get('vcodec') != 'none' and 'audio only' not in fmt.get('format', ''):
            continue
        codec = fmt.get('acodec', '').split('.')[0]
        if codec not in ('opus', 'mp4a') or not fmt.get('url'):
            continue
        size = fmt.get('filesize') or fmt.get('filesize_approx') or fmt.get('abr') or 0
        if codec not in selected or size > selected[codec][0]:
            selected[codec] = (size, fmt['url'])

    if config.CONFIG['Themerr']['BOOL_PREFER_MP4A_CODEC'] and 'mp4a' in selected:
        return selected['mp4a'][1]
    return max(selected.values(), default=(0, None))[1]


def process_youtube(url: str) -> Optional[str]:
    """
    Return the best audio stream URL from a YouTube video.

    Extract audio formats with yt-dlp and choose the largest supported stream,
    honoring the configured MP4A preference. Cookies are written to a temporary
    Netscape file for the extractor and removed afterward.

    Parameters
    ----------
    url : str
        URL of the YouTube video or playlist.

    Returns
    -------
    str or None
        Selected audio stream URL, or ``None`` if extraction fails.
    """
    cookie_dir = os.path.join(definitions.Paths.CONFIG_DIR, 'cookies')
    os.makedirs(cookie_dir, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode='w', encoding='utf-8', newline='\n', dir=cookie_dir, delete=False,
    ) as cookie_file:
        cookie_path = cookie_file.name
        _write_cookies(cookie_file, config.CONFIG['Themerr']['STR_YOUTUBE_COOKIES'])

    try:
        params = {
            'cookiefile': cookie_path,
            'logger': log,
            'socket_timeout': 10,
            'youtube_include_dash_manifest': False,
        }
        if definitions.Modes.FROZEN:
            deno_name = 'deno.exe' if sys.platform == 'win32' else 'deno'
            params['js_runtimes'] = {
                'deno': {'path': os.path.join(definitions.Paths.ROOT_DIR, deno_name)},
            }
        video = _extract_video(url, params)
        return _select_audio(video) if video else None
    finally:
        try:
            os.remove(cookie_path)
        except OSError:
            log.exception('Failed to delete YouTube cookie file: %s', cookie_path)
