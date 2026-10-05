"""Exercise real yt-dlp, audio decoding, and PlexAPI file transfers against local HTTP."""

# standard imports
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from types import SimpleNamespace
from unittest.mock import Mock

# lib imports
import av
from plexapi.mixins import ThemeMixin
import pytest
import requests

# local imports
from plex import plexapi
from plex import media as general
from themerr import storage, theme_errors
from youtube import youtube_dl


def write_audio(path, codec, duration):
    """Encode valid audio without an external FFmpeg executable."""
    samples = round(duration * 48000)
    with av.open(str(path), 'w', format='mp4' if codec == 'mp4a' else 'webm') as output:
        stream = output.add_stream('aac' if codec == 'mp4a' else 'libopus', rate=48000)
        stream.layout = 'mono'
        for offset in range(0, samples, 1024):
            frame = av.AudioFrame(format='fltp' if codec == 'mp4a' else 's16', layout='mono',
                                  samples=min(1024, samples - offset))
            frame.sample_rate = 48000
            frame.pts = offset
            for plane in frame.planes:
                plane.update(bytes(plane.buffer_size))
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)


@pytest.fixture(params=['mp4a', 'opus'])
def audio_source(request, tmp_path):
    """Provide three seconds of audio in each supported codec."""
    codec = request.param
    path = tmp_path / ('theme.m4a' if codec == 'mp4a' else 'theme.webm')
    write_audio(path, codec, 3.0)
    return path, codec


@pytest.fixture
def audio_http(audio_source):
    source_path, codec = audio_source
    source = source_path.read_bytes()
    state = {'uploaded': None, 'uploads': 0, 'truncate': False, 'reject': False, 'source_hits': 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.path == '/source':
                state['source_hits'] += 1
                data = source
            else:
                data = state['uploaded'] or b'previous theme'
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            data = self.rfile.read(int(self.headers['Content-Length']))
            state['uploads'] += 1
            if not state['reject']:
                state['uploaded'] = data[:len(data) // 2] if state['truncate'] else data
            self.send_response(406 if state['reject'] else 200)
            self.send_header('Content-Length', '0')
            self.end_headers()

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', state, source, codec
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def plex_item(base_url, state):
    """Use PlexAPI's actual file upload method with a local server adapter."""
    session = requests.Session()
    server = SimpleNamespace(_session=session, url=lambda path, **_: base_url + path,
                             _headers=lambda **headers: headers)

    def query(path, method, **kwargs):
        with method(base_url + path, **kwargs) as response:
            response.raise_for_status()

    server.query = query

    class Item(ThemeMixin):
        title = 'Local transfer test'
        type = 'movie'
        year = 2026
        ratingKey = 42
        librarySectionID = 1
        librarySectionTitle = 'Movies'
        theme = None
        guid = 'plex://movie/local'
        _server = server
        isLocked = Mock(return_value=False)

        def reload(self):
            self.theme = '/library/metadata/42/theme/audio' if state['uploaded'] else None

        def themes(self):
            return [SimpleNamespace(selected=True, provider=None, ratingKey='upload://themes/audio')]

    return Item(), session


def extract_source(monkeypatch, base_url, source, codec, duration=3.0):
    monkeypatch.setattr(youtube_dl, '_extract_video', lambda *_, **__: {
        'id': 'local', 'title': 'Local audio', 'duration': duration,
        'formats': [{'format_id': 'audio', 'url': base_url + '/source', 'vcodec': 'none',
                     'acodec': 'mp4a.40.2' if codec == 'mp4a' else 'opus',
                     'ext': 'm4a' if codec == 'mp4a' else 'webm', 'filesize': len(source)}],
    })


def test_complete_download_file_upload_and_repeated_job(configured, audio_http, monkeypatch):
    base, state, source, codec = audio_http
    extract_source(monkeypatch, base, source, codec)
    item, session = plex_item(base, state)
    configured['Themerr']['BOOL_REMOVE_UNUSED_THEMES'] = False
    configured['Themerr']['INT_PLEXAPI_UPLOAD_RETRIES_MAX'] = 0
    monkeypatch.setattr(plexapi, 'change_lock_status', Mock())
    # An unverified upload needs replacement through the complete-file path.
    general.update_themerr_data(item, {
        'youtube_theme_url': 'https://youtube.example/theme', 'uploaded_theme_key': 'upload://themes/audio',
        'audio_codec': codec, 'mp4a_available': codec == 'mp4a',
    })
    try:
        for _ in range(2):
            plexapi._update_theme(item, {'youtube_theme_url': 'https://youtube.example/theme'})
            storage.close()
        assert state['uploaded'] == source
        assert state['source_hits'] == state['uploads'] == 1
        tracked = general.get_themerr_data(item)
        assert tracked['audio_sha256']
        assert tracked['audio_codec'] == codec
        assert theme_errors.get_errors() == {}
    finally:
        session.close()


@pytest.mark.parametrize('failure', ['source_duration', 'plex_truncation', 'rejected_upload'])
def test_failed_replacement_does_not_record_success(configured, audio_http, monkeypatch, failure):
    base, state, source, codec = audio_http
    extract_source(monkeypatch, base, source, codec, duration=5.0 if failure == 'source_duration' else 3.0)
    item, session = plex_item(base, state)
    configured['Themerr']['INT_PLEXAPI_UPLOAD_RETRIES_MAX'] = 0
    configured['Themerr']['BOOL_REMOVE_UNUSED_THEMES'] = True
    removed = Mock()
    monkeypatch.setattr(general, 'remove_uploaded_media', removed)
    general.update_themerr_data(item, {'youtube_theme_url': 'previous'})
    state['truncate'] = failure == 'plex_truncation'
    state['reject'] = failure == 'rejected_upload'
    try:
        plexapi._update_theme(item, {'youtube_theme_url': 'https://youtube.example/theme'})
        assert general.get_themerr_data(item) == {'youtube_theme_url': 'previous'}
        reason = theme_errors.get_errors()['42']
        assert ('Incomplete' in reason if failure == 'source_duration' else
                'incomplete or different' in reason if failure == 'plex_truncation' else '406' in reason)
        assert state['uploads'] == (0 if failure == 'source_duration' else 1)
        removed.assert_not_called()
    finally:
        session.close()


@pytest.mark.parametrize('expected, actual', [
    (39, 39.50), (21, 21.32), (32, 32.32), (7, 7.45),
    (31, 31.42), (31, 30.64), (22, 21.55),
])
def test_whole_second_metadata_accepts_complete_audio(audio_source, tmp_path, expected, actual):
    """Accept the reported library failures when real decoded audio differs by less than a second."""
    source, codec = audio_source
    path = tmp_path / ('fractional' + source.suffix)
    write_audio(path, codec, actual)
    assert youtube_dl.validate_audio(str(path), expected, codec) == pytest.approx(actual, abs=0.1)


def test_invalid_audio_and_codec(audio_source, tmp_path):
    path, codec = audio_source
    assert youtube_dl.validate_audio(str(path), 3.0, codec) == pytest.approx(3.0, abs=0.1)
    with pytest.raises(ValueError, match='codec'):
        youtube_dl.validate_audio(str(path), 3.0, 'opus' if codec == 'mp4a' else 'mp4a')
    with pytest.raises(ValueError, match='duration is missing'):
        youtube_dl.validate_audio(str(path), float('nan'), codec)
    broken = tmp_path / 'broken.audio'
    broken.write_bytes(path.read_bytes()[:100])
    with pytest.raises((av.FFmpegError, ValueError)):
        youtube_dl.validate_audio(str(broken), 3.0, codec)
