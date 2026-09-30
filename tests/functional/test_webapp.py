"""Flask routes exercised with temporary configuration and cache data."""

import json
from pathlib import Path
import re
from unittest.mock import Mock

import pytest
import requests

from common import webapp
from plex import auth, plexapi
from themerr import theme_errors


@pytest.fixture
def client(configured, tmp_path, monkeypatch):
    webapp.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    monkeypatch.setattr(webapp, 'database_cache_file', str(tmp_path / 'dashboard.json'))
    with webapp.app.test_client() as test_client:
        yield test_client


def test_home(client, configured):
    response = client.get('/')
    assert response.status_code == 200
    assert b'Database is being cached' in response.data
    Path(webapp.database_cache_file).write_text(json.dumps({}), encoding='utf-8')
    assert client.get('/home').status_code == 200


def test_home_shows_item_failure(client, configured):
    dashboard = {'1': {
        'key': 1, 'title': 'Movies', 'agent': 'tv.plex.agents.movie', 'type': 'movie',
        'media_percent_complete': 0, 'collection_count': 0,
        'items': [{
            'rating_key': '42', 'title': 'Example', 'type': 'movie', 'year': 2020,
            'issue_action': 'add', 'issue_url': None, 'theme_provider': None,
            'theme_status': 'failed',
        }],
    }}
    Path(webapp.database_cache_file).write_text(json.dumps(dashboard), encoding='utf-8')
    theme_errors.set_error(42, 'Video unavailable')

    response = client.get('/home')
    assert response.status_code == 200
    assert b'Video unavailable' in response.data
    assert b'Example' in response.data
    theme_errors.set_error(42, '<script>alert(1)</script>')
    response = client.get('/home')
    assert b'&lt;script&gt;' in response.data
    assert b'<script>alert(1)</script>' not in response.data


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
    assert b'Sign in with Plex' in client.get('/settings/').data
    assert b'<output id="plex-auth-status"' in client.get('/settings/').data
    assert b'data-directory-target="LOG_DIR"' in client.get('/settings/').data
    assert b'data-directory-target="PLEX_APP_SUPPORT_PATH"' in client.get('/settings/').data
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
    assert plexapi.plex_server is server
    listener.assert_called_once_with()
    assert client.get('/api/plex/auth').json == {'connected': True}
    assert client.post('/api/plex/auth/check').status_code == 400

    assert client.post('/api/plex/auth/disconnect').json == {'connected': False}
    assert auth.get_token() == ''
    assert plexapi.plex_server is None
    stop_listener.assert_called_once_with()


def test_plex_sign_in_failed_server_preserves_connection(client, configured, monkeypatch):
    auth.set_token('previous-token')
    monkeypatch.setattr(auth, 'start_login', lambda: {
        'pin_id': 123, 'code': 'strong-code', 'auth_url': 'https://app.plex.tv/auth#?code=strong-code',
    })
    monkeypatch.setattr(auth, 'check_login', lambda **_: 'new-token')
    monkeypatch.setattr(plexapi, 'connect_plex_server', Mock(side_effect=RuntimeError('server unavailable')))
    assert client.post('/api/plex/auth/start').status_code == 200
    response = client.post('/api/plex/auth/check')
    assert response.status_code == 400
    assert 'could not connect' in response.json['message']
    assert auth.get_token() == 'previous-token'


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

    denied = client.post('/api/settings', data={'User_Interface|BACKGROUND_VIDEO': 'false'})
    assert denied.status_code == 400

    response = client.post(
        '/api/settings',
        data={'User_Interface|BACKGROUND_VIDEO': 'false'},
        headers={'X-CSRFToken': token},
    )
    assert response.status_code == 200
    assert response.json['status'] == 'OK'
    assert configured['User_Interface']['BACKGROUND_VIDEO'] is False


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
    original = configured['User_Interface']['BACKGROUND_VIDEO']
    monkeypatch.setattr(webapp.config, 'save_config', lambda **_: False)
    response = client.post('/api/settings', data={'User_Interface|BACKGROUND_VIDEO': 'false'})
    assert response.status_code == 500
    assert configured['User_Interface']['BACKGROUND_VIDEO'] == original


def test_translations_and_logging(client):
    assert client.get('/translations').status_code == 200
    assert client.get('/test_logger').status_code == 200
