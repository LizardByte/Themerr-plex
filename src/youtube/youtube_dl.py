"""Resolve a YouTube video's audio stream with yt-dlp."""

# standard imports
from dataclasses import dataclass, field
import json
import os
import re
import shutil
import sys
import tempfile
from typing import Callable, Optional, TextIO

# lib imports
import yt_dlp

# local imports
from common import config
from common import definitions
from common import logger

log = logger.get_logger(name=__name__)


@dataclass(frozen=True)
class AudioStream:
    """Selected audio and the codec information used to avoid duplicate uploads.

    Attributes
    ----------
    url : str
        Audio stream URL, omitted from the representation because it may be signed.
    codec : str
        Selected codec family, ``mp4a`` or ``opus``.
    mp4a_available : bool
        Whether the video offered a supported MP4A AAC stream.
    """

    url: str = field(repr=False)
    codec: str
    mp4a_available: bool


def _js_runtime() -> dict:
    """Locate a supported JavaScript runtime for yt-dlp.

    Returns
    -------
    dict
        yt-dlp runtime configuration, or an empty dictionary if none is installed.
    """
    if definitions.Modes.FROZEN:
        deno_name = 'deno.exe' if sys.platform == 'win32' else 'deno'
        return {'deno': {'path': os.path.join(definitions.Paths.ROOT_DIR, deno_name)}}

    deno = shutil.which('deno')
    if not deno:
        deno_name = 'deno.exe' if sys.platform == 'win32' else 'deno'
        bundled_deno = os.path.join(definitions.Paths.ROOT_DIR, '.build-tools', deno_name)
        deno = bundled_deno if os.path.isfile(bundled_deno) else None
    if deno:
        return {'deno': {'path': deno}}

    node = shutil.which('node')
    return {'node': {'path': node}} if node else {}


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
                str(int(cookie.get('expirationDate', cookie.get('expiry', 0)) or 0)),
                cookie['name'],
                cookie['value'],
            ]
            cookie_file.write('\t'.join(values) + '\n')
    except (ValueError, KeyError, TypeError) as exc:
        log.warning('Failed to write YouTube cookies; continuing without them: %s', exc)


def _error_reason(error: Exception) -> str:
    """Reduce an extractor error to a short message safe for the dashboard."""
    reason = re.sub(r'^(?:ERROR:\s*)?(?:\[[^]]+\]\s*[^:]+:\s*)?', '', str(error))
    reason = re.sub(r'https?://\S+', '[URL]', reason)
    return re.sub(r'\s+', ' ', reason).strip()[:300] or 'Video extraction failed'


def _extract_video(url: str, params: dict, on_error: Callable[[str], None] | None = None) -> Optional[dict]:
    """Extract a video or the first available playlist entry.

    Parameters
    ----------
    url : str
        Video or playlist URL.
    params : dict
        yt-dlp options.
    on_error : callable or None, optional
        Receives a human-readable failure reason.

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
            if on_error:
                on_error(_error_reason(exc))
            return None
        except yt_dlp.utils.DownloadError as exc:
            log.warning('yt-dlp could not extract %s: %s', url, exc)
            if on_error:
                on_error(_error_reason(exc))
            return None
        except Exception:
            log.exception('yt-dlp failed to extract %s', url)
            if on_error:
                on_error('Video extraction failed')
            return None

    if not result:
        if on_error:
            on_error('No video found')
        return None
    video = next((entry for entry in result['entries'] if entry), None) if 'entries' in result else result
    if not video and on_error:
        on_error('No video found')
    return video


def _select_audio(video: dict) -> AudioStream | None:
    """Choose the largest supported audio stream from extracted formats.

    Parameters
    ----------
    video : dict
        Extracted video data.

    Returns
    -------
    AudioStream or None
        Selected stream URL, codec, and AAC availability.
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
        codec = 'mp4a'
    elif selected:
        codec = max(selected, key=lambda value: selected[value][0])
    else:
        return None
    return AudioStream(url=selected[codec][1], codec=codec, mp4a_available='mp4a' in selected)


def process_youtube(url: str, on_error: Callable[[str], None] | None = None) -> AudioStream | None:
    """
    Return the best audio stream and its codec information from a YouTube video.

    Extract audio formats with yt-dlp and choose the largest supported stream,
    honoring the configured MP4A preference. Cookies are written to a temporary
    Netscape file for the extractor and removed afterward.

    Parameters
    ----------
    url : str
        URL of the YouTube video or playlist.
    on_error : callable or None, optional
        Receives a human-readable failure reason.

    Returns
    -------
    AudioStream or None
        Selected audio stream and codec information, or ``None`` if extraction fails.
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
            'format': 'bestaudio',
            'logger': log,
            'socket_timeout': 10,
            'youtube_include_dash_manifest': False,
        }
        runtime = _js_runtime()
        if runtime:
            params['js_runtimes'] = runtime
        video = _extract_video(url, params, on_error=on_error)
        if not video:
            return None
        audio = _select_audio(video)
        if not audio and on_error:
            on_error('No supported audio stream found')
        return audio
    finally:
        try:
            os.remove(cookie_path)
        except OSError:
            log.exception('Failed to delete YouTube cookie file: %s', cookie_path)
