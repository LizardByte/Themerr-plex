"""Download and validate complete YouTube theme audio with yt-dlp."""

# standard imports
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
from typing import Callable, Optional, TextIO

# lib imports
import av
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
    format_info : dict
        Extracted format details required by yt-dlp's downloader.
    duration : float or None
        Expected source duration in seconds.
    """

    url: str = field(repr=False)
    codec: str
    mp4a_available: bool
    format_info: dict = field(default_factory=dict, repr=False, compare=False)
    duration: float | None = None


@dataclass(frozen=True)
class AudioFile:
    """Validated temporary audio and its upload tracking information.

    Attributes
    ----------
    path : str
        Local file, valid only within the download context.
    codec : str
        ``mp4a`` or ``opus``.
    mp4a_available : bool
        Whether the source offers AAC audio.
    sha256 : str
        Digest used to verify the file Plex stores.
    duration : float
        Decoded audio duration in seconds.
    size : int
        File size in bytes.
    """

    path: str
    codec: str
    mp4a_available: bool
    sha256: str
    duration: float
    size: int


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

    video = _first_video(result)
    if not video and on_error:
        on_error('No video found')
    return video


def _first_video(result: dict | None) -> dict | None:
    """Select the first available video from an extraction result.

    Parameters
    ----------
    result : dict or None
        Extracted video or playlist data.

    Returns
    -------
    dict or None
        A video entry, or no video when extraction was empty.
    """
    if not result:
        return None
    if 'entries' in result:
        return next((entry for entry in result['entries'] if entry), None)
    return result


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
            selected[codec] = (size, fmt)

    if config.CONFIG['Themerr']['BOOL_PREFER_MP4A_CODEC'] and 'mp4a' in selected:
        codec = 'mp4a'
    elif selected:
        codec = max(selected, key=lambda value: selected[value][0])
    else:
        return None
    fmt = selected[codec][1]
    return AudioStream(url=fmt['url'], codec=codec, mp4a_available='mp4a' in selected,
                       format_info=fmt, duration=video.get('duration'))


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
    with _youtube_options() as params:
        video = _extract_video(url, params, on_error=on_error)
        if not video:
            return None
        audio = _select_audio(video)
        if not audio and on_error:
            on_error('No supported audio stream found')
        return audio


@contextmanager
def _youtube_options():
    """Keep temporary cookies available until extraction and downloading finish."""
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
            'logger': logger.YtDlpLogger(),
            'socket_timeout': 10,
            'youtube_include_dash_manifest': False,
        }
        runtime = _js_runtime()
        if runtime:
            params['js_runtimes'] = runtime
        yield params
    finally:
        try:
            os.remove(cookie_path)
        except OSError:
            log.exception('Failed to delete YouTube cookie file: %s', cookie_path)


def validate_audio(path: str, expected_duration: float, codec: str) -> float:
    """Decode every audio frame and check the source duration and codec.

    Parameters
    ----------
    path : str
        Completed download.
    expected_duration : float
        Video duration reported by the source extractor, in whole seconds for YouTube.
    codec : str
        Expected codec family.

    Returns
    -------
    float
        Decoded duration in seconds.

    Raises
    ------
    ValueError
        Audio is missing, has the wrong codec, or its duration is incomplete.
    av.FFmpegError
        The container or audio cannot be decoded.
    """
    if not expected_duration or not math.isfinite(expected_duration) or expected_duration <= 0:
        raise ValueError('Unable to verify theme audio: source duration is missing')
    with av.open(path) as container:
        if len(container.streams.audio) != 1 or container.streams.video:
            raise ValueError('Downloaded theme must contain only one audio stream')
        stream = container.streams.audio[0]
        if stream.codec_context.name != {'mp4a': 'aac', 'opus': 'opus'}[codec]:
            raise ValueError('Downloaded theme codec does not match the selected audio')
        stream.codec_context.options = {'err_detect': 'explode'}
        duration = sum(frame.samples / frame.sample_rate for frame in container.decode(stream))
    # YouTube reports whole seconds; decoded samples include fractional seconds and codec padding.
    if duration <= 0 or abs(duration - expected_duration) > 1.0:
        raise ValueError(f'Incomplete theme audio: decoded {duration:.2f}s; expected {expected_duration:.2f}s')
    return duration


@contextmanager
def download_youtube(url: str, on_error: Callable[[str], None] | None = None):
    """Download and verify a selected audio file, deleting it after the caller finishes.

    Parameters
    ----------
    url : str
        YouTube video URL.
    on_error : callable or None, optional
        Receives a safe download or validation failure reason.

    Yields
    ------
    AudioFile or None
        Complete validated audio, or ``None`` on failure.
    """
    with tempfile.TemporaryDirectory(prefix='themerr-audio-') as directory, _youtube_options() as params:
        audio_file = None
        try:
            video = _extract_video(url, params, on_error=on_error)
            audio = _select_audio(video) if video else None
            if video and not audio:
                raise ValueError('No supported audio stream found')
            if audio:
                params.update({
                    'outtmpl': os.path.join(directory, 'theme.%(ext)s'),
                    'skip_unavailable_fragments': False, 'retries': 3, 'fragment_retries': 3,
                    'fixup': 'never', 'quiet': True, 'noprogress': True,
                })
                info = {**video, **audio.format_info}
                with yt_dlp.YoutubeDL(params=params) as ydl:
                    ydl.process_info(info)
                    path = ydl.prepare_filename(info)
                if not os.path.isfile(path) or not os.path.getsize(path):
                    raise ValueError('Theme audio download did not produce a complete file')
                if audio.format_info.get('filesize') and os.path.getsize(path) != audio.format_info['filesize']:
                    raise ValueError('Incomplete theme audio: download size does not match the source')
                duration = validate_audio(path, audio.duration, audio.codec)
                with open(path, 'rb') as downloaded:
                    digest = hashlib.file_digest(downloaded, 'sha256').hexdigest()
                audio_file = AudioFile(path, audio.codec, audio.mp4a_available, digest, duration, os.path.getsize(path))
        except (yt_dlp.utils.DownloadError, av.FFmpegError, OSError, ValueError, TypeError) as error:
            reason = _error_reason(error)
            log.warning('Theme audio download or validation failed: %s', reason)
            if on_error:
                on_error(reason)
        yield audio_file
