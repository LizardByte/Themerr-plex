"""yt-dlp extraction is tested with a fake extractor and a real temporary cookie file."""

from pathlib import Path

import pytest

from youtube import youtube_dl


def extractor(monkeypatch, result=None, error=None, seen=None):
    seen = {} if seen is None else seen

    class FakeYDL:
        def __init__(self, params):
            seen['params'] = params
            seen['cookies'] = Path(params['cookiefile']).read_text(encoding='utf-8')

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def extract_info(self, **kwargs):
            seen['extract'] = kwargs
            if error:
                raise error
            return result

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

    assert youtube_dl.process_youtube('https://youtube.example/watch') == expected
    assert seen['extract'] == {'url': 'https://youtube.example/watch', 'download': False}
    assert list((Path(configured.filename).parent / 'cookies').iterdir()) == []


def test_cookies_and_bitrate_fallback(configured, monkeypatch):
    configured['Themerr']['STR_YOUTUBE_COOKIES'] = (
        '[{"domain": ".youtube.com", "path": "/", "secure": true, '
        '"name": "PREF", "value": "abc", "expiry": 123}]'
    )
    seen = extractor(monkeypatch, {'formats': [
        {'format': 'audio only', 'acodec': 'opus', 'abr': 128, 'url': 'https://opus'},
    ]})
    assert youtube_dl.process_youtube('https://youtube.example') == 'https://opus'
    assert '.youtube.com\tTRUE\t/\tTRUE\t123\tPREF\tabc' in seen['cookies']


@pytest.mark.parametrize('result', [None, {'entries': []}, {'formats': []}])
def test_no_audio(configured, monkeypatch, result):
    extractor(monkeypatch, result)
    assert youtube_dl.process_youtube('https://youtube.example') is None


def test_extractor_error_and_invalid_cookies(configured, monkeypatch):
    configured['Themerr']['STR_YOUTUBE_COOKIES'] = 'not json'
    seen = extractor(
        monkeypatch, error=youtube_dl.yt_dlp.utils.ExtractorError('unavailable', expected=True),
    )
    assert youtube_dl.process_youtube('https://youtube.example') is None
    assert seen['cookies'].startswith('# Netscape HTTP Cookie File')
    assert not Path(seen['params']['cookiefile']).exists()


def test_download_error_is_nonfatal(configured, monkeypatch):
    seen = extractor(monkeypatch, error=youtube_dl.yt_dlp.utils.DownloadError('Video unavailable'))
    assert youtube_dl.process_youtube('https://youtube.example') is None
    assert seen['params']['format'] == 'bestaudio'


def test_unexpected_error(configured, monkeypatch):
    extractor(monkeypatch, error=RuntimeError('failed'))
    assert youtube_dl.process_youtube('https://youtube.example') is None


def test_ns_bool():
    assert youtube_dl.ns_bool(True) == 'TRUE'
    assert youtube_dl.ns_bool(False) == 'FALSE'


def test_frozen_build_uses_bundled_deno(configured, monkeypatch, tmp_path):
    monkeypatch.setattr(youtube_dl.definitions.Modes, 'FROZEN', True)
    monkeypatch.setattr(youtube_dl.definitions.Paths, 'ROOT_DIR', str(tmp_path))
    seen = extractor(monkeypatch, {'formats': []})
    assert youtube_dl.process_youtube('https://youtube.example') is None
    name = 'deno.exe' if youtube_dl.sys.platform == 'win32' else 'deno'
    assert seen['params']['js_runtimes'] == {'deno': {'path': str(tmp_path / name)}}


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
