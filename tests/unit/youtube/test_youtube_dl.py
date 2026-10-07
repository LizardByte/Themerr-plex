"""yt-dlp extraction uses mocked network calls and in-memory cookies."""

# standard imports
from contextlib import nullcontext
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

# lib imports
import pytest

# local imports
from common import config, credentials
from youtube import youtube_dl


def extractor(monkeypatch, result=None, error=None, seen=None, payload=b'audio', download_error=None):
    seen = {} if seen is None else seen

    class FakeYDL:
        def __init__(self, params):
            seen['params'] = params
            seen['cookies'] = params['cookiefile'].getvalue()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def extract_info(self, **kwargs):
            seen['extract'] = kwargs
            if error:
                raise error
            return result

        def process_info(self, info):
            seen['download_info'] = info
            Path(self.prepare_filename(info)).write_bytes(payload)
            if download_error:
                raise download_error

        def prepare_filename(self, info):
            return seen['params']['outtmpl'].replace('%(ext)s', info.get('ext', 'm4a'))

    monkeypatch.setattr(youtube_dl.yt_dlp, 'YoutubeDL', FakeYDL)
    return seen


@pytest.mark.parametrize('prefer_mp4a, expected', [
    (False, 'https://opus'),
    (True, 'https://mp4a'),
])
def test_select_audio(configured, monkeypatch, prefer_mp4a, expected):
    configured['Themerr']['BOOL_PREFER_MP4A_CODEC'] = prefer_mp4a
    formats = [
        {'vcodec': 'none', 'acodec': 'opus', 'filesize': 200, 'url': 'https://opus'},
        {'vcodec': 'none', 'acodec': 'mp4a.40.2', 'filesize_approx': 100, 'url': 'https://mp4a'},
        {'vcodec': 'h264', 'acodec': 'mp4a', 'filesize': 1000, 'url': 'https://video'},
        {'vcodec': 'none', 'acodec': 'vorbis', 'filesize': 300, 'url': 'https://other'},
    ]
    seen = extractor(monkeypatch, {'entries': [None, {'formats': formats}]})

    audio = youtube_dl.process_youtube('https://youtube.example/watch')
    assert audio.url == expected
    assert audio.codec == ('mp4a' if prefer_mp4a else 'opus')
    assert audio.mp4a_available is True
    assert seen['extract'] == {'url': 'https://youtube.example/watch', 'download': False}
    assert not (Path(configured.filename).parent / 'cookies').exists()
    assert seen['params']['cookiefile'].closed


@pytest.mark.parametrize('expiry_field, expiry, expected', [
    ('expiry', 123, 123),
    ('expirationDate', 123.9, 123),
    ('session', True, 0),
])
def test_cookies_and_bitrate_fallback(configured, monkeypatch, expiry_field, expiry, expected):
    configured['Themerr']['STR_YOUTUBE_COOKIES'] = json.dumps([{
        'domain': '.youtube.com', 'path': '/', 'secure': True,
        'name': 'PREF', 'value': 'abc', expiry_field: expiry,
    }])
    assert config.save_config(config=configured)
    seen = extractor(monkeypatch, {'formats': [
        {'format': 'audio only', 'acodec': 'opus', 'abr': 128, 'url': 'https://opus'},
    ]})
    assert youtube_dl.process_youtube('https://youtube.example') == youtube_dl.AudioStream(
        url='https://opus', codec='opus', mp4a_available=False)
    assert f'.youtube.com\tTRUE\t/\tTRUE\t{expected}\tPREF\tabc' in seen['cookies']


@pytest.mark.parametrize('result', [None, {'entries': []}, {'formats': []}])
def test_no_audio(configured, monkeypatch, result):
    extractor(monkeypatch, result)
    assert youtube_dl.process_youtube('https://youtube.example') is None


def test_extractor_error_and_invalid_cookies(configured, monkeypatch):
    configured['Themerr']['STR_YOUTUBE_COOKIES'] = 'not json'
    assert config.save_config(config=configured)
    seen = extractor(
        monkeypatch, error=youtube_dl.yt_dlp.utils.ExtractorError('unavailable', expected=True),
    )
    assert youtube_dl.process_youtube('https://youtube.example') is None
    assert seen['cookies'].startswith('# Netscape HTTP Cookie File')
    assert seen['params']['cookiefile'].closed


def test_download_error_is_nonfatal(configured, monkeypatch):
    seen = extractor(monkeypatch, error=youtube_dl.yt_dlp.utils.DownloadError(
        'ERROR: [youtube] Y8r_oMQqOIY: Video unavailable'))
    errors = []
    assert youtube_dl.process_youtube('https://youtube.example', on_error=errors.append) is None
    assert errors == ['Video unavailable']
    assert seen['params']['format'] == 'bestaudio'


def test_unexpected_error(configured, monkeypatch):
    extractor(monkeypatch, error=RuntimeError('failed'))
    assert youtube_dl.process_youtube('https://youtube.example') is None


def test_ns_bool():
    assert youtube_dl.ns_bool(True) == 'TRUE'
    assert youtube_dl.ns_bool(False) == 'FALSE'


def test_frozen_build_uses_bundled_deno(configured, monkeypatch, tmp_path):
    monkeypatch.setattr(youtube_dl.definitions.Modes, 'FROZEN', True)
    monkeypatch.setattr(youtube_dl.definitions.Modes, 'DOCKER', False)
    monkeypatch.setattr(youtube_dl.definitions.Paths, 'ROOT_DIR', str(tmp_path))
    seen = extractor(monkeypatch, {'formats': []})
    assert youtube_dl.process_youtube('https://youtube.example') is None
    name = 'deno.exe' if youtube_dl.sys.platform == 'win32' else 'deno'
    assert seen['params']['js_runtimes'] == {'deno': {'path': str(tmp_path / name)}}


def test_frozen_docker_build_uses_installed_deno(configured, monkeypatch, tmp_path):
    monkeypatch.setattr(youtube_dl.definitions.Modes, 'FROZEN', True)
    monkeypatch.setattr(youtube_dl.definitions.Modes, 'DOCKER', True)
    monkeypatch.setattr(youtube_dl.definitions.Paths, 'ROOT_DIR', str(tmp_path))
    monkeypatch.setattr(youtube_dl.shutil, 'which', lambda executable: '/tools/deno' if executable == 'deno' else None)
    seen = extractor(monkeypatch, {'formats': []})

    assert youtube_dl.process_youtube('https://youtube.example') is None
    assert seen['params']['js_runtimes'] == {'deno': {'path': '/tools/deno'}}


def test_source_build_uses_local_deno(configured, monkeypatch, tmp_path):
    monkeypatch.setattr(youtube_dl.definitions.Modes, 'FROZEN', False)
    monkeypatch.setattr(youtube_dl.definitions.Paths, 'ROOT_DIR', str(tmp_path))
    monkeypatch.setattr(youtube_dl.shutil, 'which', lambda _: None)
    deno_name = 'deno.exe' if youtube_dl.sys.platform == 'win32' else 'deno'
    local_deno = tmp_path / '.build-tools' / deno_name
    local_deno.parent.mkdir()
    local_deno.touch()
    seen = extractor(monkeypatch, {'formats': []})

    assert youtube_dl.process_youtube('https://youtube.example') is None
    assert seen['params']['js_runtimes'] == {'deno': {'path': str(local_deno)}}


def test_source_build_falls_back_to_node(configured, monkeypatch, tmp_path):
    monkeypatch.setattr(youtube_dl.definitions.Modes, 'FROZEN', False)
    monkeypatch.setattr(youtube_dl.definitions.Paths, 'ROOT_DIR', str(tmp_path))
    monkeypatch.setattr(youtube_dl.shutil, 'which', lambda executable: '/tools/node' if executable == 'node' else None)
    seen = extractor(monkeypatch, {'formats': []})

    assert youtube_dl.process_youtube('https://youtube.example') is None
    assert seen['params']['js_runtimes'] == {'node': {'path': '/tools/node'}}


def test_complete_download_context_and_cleanup(configured, monkeypatch):
    seen = extractor(monkeypatch, {'duration': 60, 'formats': [
        {'vcodec': 'none', 'acodec': 'mp4a.40.2', 'ext': 'm4a', 'url': 'https://signed-audio',
         'http_headers': {'Referer': 'https://youtube.example'}, 'filesize': 5},
    ]})
    monkeypatch.setattr(youtube_dl, 'validate_audio', lambda *_: 60.0)
    with youtube_dl.download_youtube('https://youtube.example') as audio:
        path = Path(audio.path)
        assert path.read_bytes() == b'audio'
        assert audio.codec == 'mp4a'
        assert audio.size == 5
        assert len(audio.sha256) == 64
        assert not seen['params']['cookiefile'].closed
        assert seen['params']['skip_unavailable_fragments'] is False
        assert seen['params']['fixup'] == 'never'
        assert seen['download_info']['http_headers'] == {'Referer': 'https://youtube.example'}
    assert not path.parent.exists()
    assert seen['params']['cookiefile'].closed


def test_empty_decoded_audio_is_rejected(monkeypatch):
    """Duration rounding must not allow a header-only file for a short video."""
    stream = SimpleNamespace(codec_context=SimpleNamespace(name='aac', options={}))
    container = SimpleNamespace(streams=SimpleNamespace(audio=[stream], video=[]),
                                decode=Mock(return_value=iter(())))
    monkeypatch.setattr(youtube_dl.av, 'open', lambda _: nullcontext(container))
    with pytest.raises(ValueError, match='Incomplete theme audio'):
        youtube_dl.validate_audio('header-only.m4a', 1.0, 'mp4a')


@pytest.mark.parametrize('failure', ['fragment', 'size', 'validation', 'empty'])
def test_failed_download_is_not_usable_and_is_cleaned(configured, monkeypatch, failure):
    seen = extractor(monkeypatch, {'duration': 60, 'formats': [
        {'vcodec': 'none', 'acodec': 'opus', 'url': 'https://signed-audio', 'ext': 'webm',
         'filesize': 99 if failure == 'size' else 5},
    ]}, payload=b'' if failure == 'empty' else b'audio', download_error=(
        youtube_dl.yt_dlp.utils.DownloadError('fragment unavailable') if failure == 'fragment' else None))
    monkeypatch.setattr(youtube_dl, 'validate_audio', lambda *_: (_ for _ in ()).throw(ValueError('Incomplete audio')))
    errors = []
    with youtube_dl.download_youtube('https://youtube.example', on_error=errors.append) as audio:
        assert audio is None
    assert len(errors) == 1
    path = Path(seen['params']['outtmpl']).parent
    assert not path.exists()
    assert seen['params']['cookiefile'].closed


def test_real_cookie_jar_can_load_and_rewrite_without_a_file(configured):
    configured['Themerr']['STR_YOUTUBE_COOKIES'] = json.dumps([{
        'domain': '.youtube.com',
        'path': '/',
        'secure': True,
        'name': 'SESSION',
        'value': 'private-session',
    }])
    assert config.save_config(config=configured)
    with youtube_dl._youtube_options() as params:
        for _ in range(2):
            params['cookiefile'].seek(0)
            with youtube_dl.yt_dlp.YoutubeDL(params) as ydl:
                assert ydl.cookiejar.get_cookie_header('https://www.youtube.com/') == 'SESSION=private-session'
            assert '\0' not in params['cookiefile'].getvalue()
    assert params['cookiefile'].closed
    assert not (Path(configured.filename).parent / 'cookies').exists()


def test_unavailable_cookie_key_does_not_escape_or_leak(configured, monkeypatch):
    configured['Themerr']['STR_YOUTUBE_COOKIES'] = credentials.SETTING_PREFIX + 'unreadable'
    seen = extractor(monkeypatch, {'formats': []})
    assert youtube_dl.process_youtube('https://youtube.example') is None
    assert seen['cookies'] == '# Netscape HTTP Cookie File\n'
    assert seen['params']['cookiefile'].closed
