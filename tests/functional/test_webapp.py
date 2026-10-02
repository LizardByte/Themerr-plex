"""Flask routes exercised with temporary configuration and cache data."""

# standard imports
import re
from types import SimpleNamespace
from unittest.mock import Mock

# lib imports
import pytest
import requests
from plexapi.exceptions import NotFound
from sqlalchemy.orm import Session

# local imports
from common import admin, webapp
from plex import servers
from plex import auth, plexapi
from themerr import storage
from themerr import theme_errors


@pytest.fixture
def client(configured, tmp_path, monkeypatch):
    webapp.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SESSION_COOKIE_SECURE=False)
    monkeypatch.setattr(admin, 'HASH_METHOD', 'scrypt:16384:8:1')
    current = admin._save('admin', 'a unique test password')
    with Session(storage.engine()) as database:
        database.add(servers.ServerRecord(id='default', name='Plex', url='http://plex.example'))
        database.commit()
    with webapp.app.test_client() as test_client:
        with test_client.session_transaction() as browser_session:
            browser_session['admin_revision'] = current['revision']
        yield test_client


def _dashboard(items):
    """Build a small persisted library snapshot for route tests."""
    return {'1': {
        'key': 1, 'title': 'Movies', 'agent': 'tv.plex.agents.movie', 'type': 'movie',
        'media_count': len(items), 'media_percent_complete': 0,
        'collection_count': 0, 'collection_percent_complete': 0,
        'collections_enabled': False, 'total_count': len(items), 'items': items,
    }}


def test_home(client, configured):
    response = client.get('/')
    assert response.status_code == 200
    assert b'Getting to know your library.' in response.data
    storage.replace_dashboard(_dashboard([]))
    assert client.get('/home').status_code == 200


def test_asset_urls_change_when_compiled_content_changes(client, monkeypatch, tmp_path):
    monkeypatch.setattr(webapp.app, 'static_folder', str(tmp_path))
    css = tmp_path / 'app.css'
    css.write_text('body {color: red}', encoding='utf-8')
    with webapp.app.test_request_context():
        first = webapp.asset_url('app.css')
        assert first == webapp.asset_url('app.css')
        css.write_text('body {color: green}', encoding='utf-8')
        second = webapp.asset_url('app.css')
        assert first != second
        assert webapp.asset_url('missing.css') == '/web/assets/missing.css'
    assert b'href="' + second.encode() + b'"' in client.get('/').data


def test_branding_uses_the_project_asset_and_links(client):
    page = client.get('/').data
    assert b'class="brand-logo"' in page
    assert b'src="/images/icon-default.png"' in page
    assert b'href="https://app.lizardbyte.dev/" target="_blank" rel="noopener noreferrer"' in page
    assert b'href="https://github.com/LizardByte/Themerr-plex" target="_blank" rel="noopener noreferrer"' in page
    for body in re.findall(rb'<a\b[^>]*target="_blank"[^>]*>(.*?)</a>', page, re.DOTALL):
        assert b'data-lucide="arrow-up-right"' in body


def test_theme_controls_only_for_installed_themes(client):
    providers = ['plex', 'user', 'themerr', 'uploaded', None]
    items = [{
        'rating_key': str(index), 'title': f'Theme {index}', 'type': 'movie', 'year': 2020,
        'issue_url': None, 'theme_provider': provider, 'theme_status': 'complete', 'theme': True,
    } for index, provider in enumerate(providers, start=1)]
    items.append({
        'rating_key': '99', 'title': 'No theme', 'type': 'show', 'year': 2020,
        'issue_url': None, 'theme_provider': None, 'theme_status': 'pending', 'theme': False,
    })
    storage.replace_dashboard(_dashboard(items))

    page = client.get('/home').data
    for index in range(1, 6):
        assert f'data-theme-url="/api/themes/{index}"'.encode() in page
    assert b'data-theme-url="/api/themes/99"' not in page
    assert page.count(b'data-lucide="play"') == len(providers)
    assert page.count(b'id="theme-player"') == 1
    assert b'preload="none"' in page


@pytest.fixture
def theme_server(monkeypatch):
    server = Mock()
    server.fetchItem.return_value = SimpleNamespace(theme='/library/metadata/42/theme/123')
    server.url.return_value = 'http://plex.example/library/metadata/42/theme/123'
    server._headers.side_effect = lambda **headers: {'X-Plex-Token': 'private-token', **headers}
    upstream = Mock(status_code=200, headers={
        'Content-Type': 'audio/mpeg', 'Content-Length': '6', 'Accept-Ranges': 'bytes',
        'X-Plex-Token': 'private-token', 'Location': 'http://plex.example/?X-Plex-Token=private-token',
    })
    upstream.iter_content.return_value = iter([b'abc', b'def'])
    server._session.get.return_value = upstream
    monkeypatch.setattr(plexapi, 'setup_plexapi', lambda: server)
    return server, upstream


@pytest.mark.parametrize('partial', [False, True])
def test_theme_audio_stream_and_ranges(client, theme_server, partial):
    server, upstream = theme_server
    headers = {}
    if partial:
        headers = {'Range': 'bytes=0-5', 'If-Range': 'theme-version'}
        upstream.status_code = 206
        upstream.headers['Content-Range'] = 'bytes 0-5/10'
    response = client.get('/api/themes/42', headers=headers)

    assert response.status_code == upstream.status_code
    assert response.data == b'abcdef'
    assert response.content_type == 'audio/mpeg'
    assert response.headers['Content-Length'] == '6'
    assert response.headers['Accept-Ranges'] == 'bytes'
    assert response.headers['Cache-Control'] == 'no-store'
    assert 'X-Plex-Token' not in response.headers
    assert 'Location' not in response.headers
    if partial:
        assert response.headers['Content-Range'] == 'bytes 0-5/10'
    server.fetchItem.assert_called_once_with(42)
    server.url.assert_called_once_with('/library/metadata/42/theme/123', includeToken=False)
    forwarded = server._session.get.call_args.kwargs
    assert forwarded['stream'] is True
    assert forwarded['allow_redirects'] is False
    assert forwarded['headers'] == {'X-Plex-Token': 'private-token', 'Accept-Encoding': 'identity', **headers}
    response.close()
    upstream.close.assert_called()


def test_theme_head_closes_without_reading_audio(client, theme_server):
    _, upstream = theme_server
    response = client.head('/api/themes/42')
    assert response.status_code == 200
    assert response.data == b''
    assert response.headers['Content-Length'] == '6'
    upstream.iter_content.assert_not_called()
    upstream.close.assert_called_once()


def test_theme_proxy_does_not_serve_upstream_html_on_the_application_origin(client, theme_server):
    _, upstream = theme_server
    upstream.headers['Content-Type'] = 'text/html'
    response = client.get('/api/themes/42')
    assert response.status_code == 502
    assert response.json['message'] == 'Plex returned an unsupported audio format.'
    upstream.iter_content.assert_not_called()
    upstream.close.assert_called_once()


@pytest.mark.parametrize('theme, status', [
    (None, 404),
    ('https://other.example/theme/123', 502),
    ('//other.example/library/metadata/42/theme/123', 502),
])
def test_theme_missing_or_invalid_path(client, theme_server, theme, status):
    server, _ = theme_server
    server.fetchItem.return_value.theme = theme
    response = client.get('/api/themes/42')
    assert response.status_code == status
    server._session.get.assert_not_called()


def test_theme_requires_plex_connection(client, monkeypatch):
    monkeypatch.setattr(plexapi, 'setup_plexapi', lambda: None)
    assert client.get('/api/themes/42').status_code == 503
    assert client.get('/api/themes/not-an-id').status_code == 404


@pytest.mark.parametrize('error, status', [
    (NotFound('private-token'), 404),
    (requests.Timeout('private-token'), 502),
])
def test_theme_lookup_errors_are_sanitized(client, theme_server, caplog, error, status):
    server, _ = theme_server
    server.fetchItem.side_effect = error
    response = client.get('/api/themes/42')
    assert response.status_code == status
    assert b'private-token' not in response.data
    assert 'private-token' not in caplog.text


@pytest.mark.parametrize('status, expected', [(302, 502), (404, 404), (500, 502), (416, 416)])
def test_theme_upstream_errors_close_connection(client, theme_server, status, expected):
    _, upstream = theme_server
    upstream.status_code = status
    upstream.headers['Content-Range'] = 'bytes */6'
    response = client.get('/api/themes/42')
    assert response.status_code == expected
    assert b'private-token' not in response.data
    if status == 416:
        assert response.headers['Content-Range'] == 'bytes */6'
        assert response.headers['Content-Length'] == '0'
    upstream.iter_content.assert_not_called()
    upstream.close.assert_called_once()


def test_theme_interrupted_stream_is_closed(client, theme_server, caplog):
    _, upstream = theme_server

    def interrupted_audio(**kwargs):
        yield b'abc'
        raise requests.ConnectionError('private-token')

    upstream.iter_content.side_effect = interrupted_audio
    response = client.get('/api/themes/42')
    assert response.data == b'abc'
    upstream.close.assert_called()
    assert 'Theme playback interrupted for rating_key=42' in caplog.text
    assert 'private-token' not in caplog.text


def test_theme_cancelled_playback_closes_connection(client, theme_server):
    _, upstream = theme_server
    response = client.get('/api/themes/42', buffered=False)
    assert next(iter(response.response)) == b'abc'
    response.close()
    upstream.close.assert_called()


def test_home_shows_item_failure(client, configured):
    dashboard = _dashboard([{
            'rating_key': '42', 'title': 'Example', 'type': 'movie', 'year': 2020,
            'issue_action': 'add', 'issue_url': None, 'theme_provider': None,
            'theme_status': 'pending', 'theme': False,
        }])
    storage.replace_dashboard(dashboard)
    assert b'Theme not installed yet' in client.get('/home').data
    theme_errors.set_error(42, 'Video unavailable')

    response = client.get('/home')
    assert response.status_code == 200
    assert b'Video unavailable' in response.data
    assert b'Failed to add theme' in response.data
    assert b'Example' in response.data
    theme_errors.set_error(42, '<script>alert(1)</script>')
    response = client.get('/home')
    assert b'&lt;script&gt;' in response.data
    assert b'<script>alert(1)</script>' not in response.data


def test_home_reflects_successful_upload_on_reload(client):
    storage.replace_dashboard(_dashboard([{
        'rating_key': '42', 'title': 'Example', 'type': 'movie', 'year': 2020,
        'issue_action': 'add', 'issue_url': None, 'theme_provider': None,
        'theme_status': 'pending', 'theme': False,
    }]))
    assert b'Theme not installed yet' in client.get('/home').data

    storage.mark_dashboard_theme_uploaded(42, 'themerr')

    response = client.get('/home')
    assert response.status_code == 200
    assert b'Themerr provided' in response.data
    assert b'Theme not installed yet' not in response.data


def test_home_distinguishes_external_id_and_unknown_provider(client, configured):
    storage.replace_dashboard(_dashboard([
        {
            'rating_key': '42', 'title': 'TV example', 'type': 'show', 'year': 2020,
            'source_database': 'thetvdb', 'source_id': '123', 'issue_url': None,
            'theme_provider': None, 'theme_status': 'unresolved', 'theme': False,
        },
        {
            'rating_key': '43', 'title': 'Movie example', 'type': 'movie', 'year': 2021,
            'issue_url': None, 'theme_provider': 'uploaded', 'theme_status': 'complete', 'theme': True,
        },
        {
            'rating_key': '44', 'title': 'Unattributed theme', 'type': 'movie', 'year': 2022,
            'issue_url': None, 'theme_provider': None, 'theme_status': 'complete', 'theme': True,
        },
    ]))

    response = client.get('/home')
    assert response.status_code == 200
    page = re.sub(rb'\s+', b' ', response.data)
    assert b'TVDB 123' in page
    assert b'TMDB ID unavailable' in page
    assert page.count(b'Unknown provider') == 2
    assert b'Plex ID: 43' in page


def test_home_shows_failed_replacement_of_unknown_provider(client):
    storage.replace_dashboard(_dashboard([
        {
            'rating_key': '43', 'title': 'Uploaded theme', 'type': 'movie', 'year': 2021,
            'issue_url': None, 'theme_provider': 'uploaded', 'theme_status': 'complete', 'theme': True,
        },
        {
            'rating_key': '44', 'title': 'Unattributed theme', 'type': 'movie', 'year': 2022,
            'issue_url': None, 'theme_provider': None, 'theme_status': 'complete', 'theme': True,
        },
    ]))
    theme_errors.set_error(43, 'Plex rejected the replacement')
    theme_errors.set_error(44, 'Video unavailable')

    page = re.sub(rb'\s+', b' ', client.get('/home').data)
    assert page.count(b'Unknown provider') == 2
    assert page.count(b'Outdated from ThemerrDB') == 2
    assert b'Plex rejected the replacement' in page
    assert b'Video unavailable' in page
    assert b'Failed to add theme' not in page
    assert page.count(b'class="failure-reason"') == 2

    theme_errors.set_error(43, None)
    page = client.get('/home').data
    assert page.count(b'Outdated from ThemerrDB') == 1
    assert b'Plex rejected the replacement' not in page


def test_images_and_status(client):
    assert client.get('/favicon.ico').content_type == 'image/vnd.microsoft.icon'
    assert client.get('/images/missing.png').status_code == 404
    assert client.get('/status').json == {'result': 'success', 'message': 'Ok'}


def test_settings(client):
    assert client.get('/settings/').status_code == 200
    assert client.get('/settings/plugin/example').status_code == 404
    response = client.get('/api/settings')
    assert response.status_code == 200
    assert 'Themerr' in response.json
    assert 'PLEX_TOKEN' not in response.json['Plex']
    assert b'Your Plex account' in client.get('/servers').data
    assert b'id="plex-auth-status"' in client.get('/servers').data
    assert b'data-directory-target="LOG_DIR"' in client.get('/settings/').data
    assert b'Plex data directory' in client.get('/servers').data
    assert b'PLEX_TOKEN' not in client.get('/settings/').data


def test_directory_browser_lists_server_folders(client, tmp_path):
    child = tmp_path / 'Plex Media Server'
    child.mkdir()
    (tmp_path / 'private.txt').write_text('not listed', encoding='utf-8')
    assert re.fullmatch(webapp.config.regex_directory, str(child))

    response = client.post('/api/directories', json={'path': str(tmp_path)})

    assert response.status_code == 200
    assert response.json['path'] == str(tmp_path)
    assert response.json['directories'] == [{'name': child.name, 'path': str(child)}]
    assert response.json['parent'] == str(tmp_path.parent)
    assert client.post('/api/directories', json={'path': str(tmp_path / 'missing')}).status_code == 400
    assert client.post('/api/directories', json={'path': 'relative/path'}).status_code == 400


def test_directory_browser_requires_csrf(client, tmp_path):
    webapp.app.config['WTF_CSRF_ENABLED'] = True
    page = client.get('/settings/')
    csrf_token = re.search(rb'data-csrf-token="([^"]+)"', page.data).group(1).decode()

    assert client.post('/api/directories', json={'path': str(tmp_path)}).status_code == 400
    response = client.post('/api/directories', json={'path': str(tmp_path)},
                           headers={'X-CSRFToken': csrf_token})
    assert response.status_code == 200


def test_plex_sign_in_requires_csrf(client, configured, monkeypatch):
    webapp.app.config['WTF_CSRF_ENABLED'] = True
    page = client.get('/settings/')
    csrf_token = re.search(rb'data-csrf-token="([^"]+)"', page.data).group(1).decode()
    monkeypatch.setattr(auth, 'start_login', lambda: {
        'pin_id': 123, 'code': 'strong-code', 'auth_url': 'https://app.plex.tv/auth#?code=strong-code',
    })
    assert client.post('/api/plex/auth/start').status_code == 400
    assert client.post('/api/plex/auth/start', headers={'X-CSRFToken': csrf_token}).status_code == 200
    assert client.post('/api/plex/auth/check').status_code == 400
    assert client.post('/api/plex/auth/disconnect').status_code == 400


def test_plex_sign_in_flow(client, configured, monkeypatch):
    monkeypatch.setattr(auth, 'start_login', lambda: {
        'pin_id': 123, 'code': 'strong-code', 'auth_url': 'https://app.plex.tv/auth#?code=strong-code',
    })
    check = iter(['', 'issued-token'])
    monkeypatch.setattr(auth, 'check_login', lambda **_: next(check))
    server = object()
    monkeypatch.setattr(plexapi, 'connect_plex_server', Mock(return_value=server))
    monkeypatch.setattr(plexapi, 'plex_server', None)
    listener = Mock()
    stop_listener = Mock()
    monkeypatch.setattr(plexapi, 'plex_listener', listener)
    monkeypatch.setattr(plexapi, 'stop_plex_listener', stop_listener)

    assert client.get('/api/plex/auth').json == {'connected': False}
    assert client.post('/api/plex/auth/check').status_code == 400
    assert client.post('/api/plex/auth/start').json['auth_url'].startswith('https://app.plex.tv/auth#?')
    assert client.post('/api/plex/auth/check').status_code == 202
    assert client.get('/api/plex/auth').json == {'connected': False}
    assert client.post('/api/plex/auth/check').json == {'connected': True}
    assert auth.get_token() == 'issued-token'
    assert plexapi.plex_server is None
    listener.assert_not_called()
    assert client.get('/api/plex/auth').json == {'connected': True}
    assert client.post('/api/plex/auth/check').status_code == 400

    assert client.post('/api/plex/auth/disconnect').json == {'connected': False}
    assert auth.get_token() == ''
    assert plexapi.plex_server is None
    stop_listener.assert_called()


def test_account_sign_in_does_not_require_a_preconfigured_server(client, configured, monkeypatch):
    auth.set_token('previous-token')
    monkeypatch.setattr(auth, 'start_login', lambda: {
        'pin_id': 123, 'code': 'strong-code', 'auth_url': 'https://app.plex.tv/auth#?code=strong-code',
    })
    monkeypatch.setattr(auth, 'check_login', lambda **_: 'new-token')
    monkeypatch.setattr(plexapi, 'connect_plex_server', Mock(side_effect=RuntimeError('server unavailable')))
    assert client.post('/api/plex/auth/start').status_code == 200
    response = client.post('/api/plex/auth/check')
    assert response.status_code == 200
    assert auth.get_token() == 'new-token'
    plexapi.connect_plex_server.assert_not_called()


def test_plex_sign_in_requires_secure_store(client, configured, monkeypatch):
    monkeypatch.setenv('THEMERR_DOCKER', 'True')
    monkeypatch.setattr(auth, 'start_login', lambda: {
        'pin_id': 123, 'code': 'strong-code', 'auth_url': 'https://app.plex.tv/auth#?code=strong-code',
    })
    monkeypatch.setattr(auth, 'check_login', lambda **_: 'issued-token')
    monkeypatch.setattr(plexapi, 'connect_plex_server', Mock(return_value=object()))

    assert client.post('/api/plex/auth/start').status_code == 200
    response = client.post('/api/plex/auth/check')
    assert response.status_code == 500
    assert response.json == {'message': 'Unable to save Plex sign-in.'}
    assert auth.get_token() == ''
    assert storage.get_encrypted_token() == ''


def test_plex_sign_in_expired_and_upstream_failure(client, configured, monkeypatch):
    monkeypatch.setattr(auth, 'start_login', lambda: {
        'pin_id': 123, 'code': 'strong-code', 'auth_url': 'https://app.plex.tv/auth#?code=strong-code',
    })
    monkeypatch.setattr(auth, 'check_login', Mock(side_effect=RuntimeError('not called')))
    client.post('/api/plex/auth/start')
    with client.session_transaction() as browser_session:
        browser_session['plex_login']['started'] -= webapp.PLEX_LOGIN_LIFETIME + 1
        browser_session.modified = True
    assert client.post('/api/plex/auth/check').status_code == 410
    assert client.post('/api/plex/auth/check').status_code == 400

    monkeypatch.setattr(auth, 'start_login', Mock(side_effect=requests.Timeout('upstream')))
    assert client.post('/api/plex/auth/start').status_code == 502


def test_plex_pin_expired_upstream(client, configured, monkeypatch):
    monkeypatch.setattr(auth, 'start_login', lambda: {
        'pin_id': 123, 'code': 'strong-code', 'auth_url': 'https://app.plex.tv/auth#?code=strong-code',
    })
    response = requests.Response()
    response.status_code = 404
    monkeypatch.setattr(auth, 'check_login', Mock(side_effect=requests.HTTPError(response=response)))
    assert client.post('/api/plex/auth/start').status_code == 200
    assert client.post('/api/plex/auth/check').status_code == 410
    assert client.post('/api/plex/auth/check').status_code == 400


def test_save_settings_with_csrf(client, configured):
    webapp.app.config['WTF_CSRF_ENABLED'] = True
    page = client.get('/settings/')
    token = re.search(rb'data-csrf-token="([^"]+)"', page.data).group(1).decode()

    denied = client.post('/api/settings', data={'General|LAUNCH_BROWSER': 'false'})
    assert denied.status_code == 400

    response = client.post(
        '/api/settings',
        data={'General|LAUNCH_BROWSER': 'false'},
        headers={'X-CSRFToken': token},
    )
    assert response.status_code == 200
    assert response.json['status'] == 'OK'
    assert configured['General']['LAUNCH_BROWSER'] is False


def test_reject_invalid_settings_without_mutating_config(client, configured):
    original_port = configured['Network']['HTTP_PORT']
    for data in (
        {'Network|HTTP_PORT': '99999'},
        {'Network|HTTP_PORT': 'not a number'},
        {'Info|CONFIG_VERSION': '2'},
        {'Plex|PLEX_TOKEN': 'manual-token'},
        {'unknown': 'value'},
    ):
        response = client.post('/api/settings', data=data)
        assert response.status_code == 400
        assert response.json['status'] == 'ERROR'
        assert configured['Network']['HTTP_PORT'] == original_port


def test_save_failure_restores_config(client, configured, monkeypatch):
    original = configured['General']['LAUNCH_BROWSER']
    monkeypatch.setattr(webapp.config, 'save_config', lambda **_: False)
    response = client.post('/api/settings', data={'General|LAUNCH_BROWSER': 'false'})
    assert response.status_code == 500
    assert configured['General']['LAUNCH_BROWSER'] == original


def test_translations_and_logging(client):
    assert client.get('/translations').status_code == 200
    assert client.post('/test_logger').status_code == 200
