"""Flask routes exercised with temporary configuration and cache data."""

import json
from pathlib import Path
import re

import pytest

from common import webapp


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


def test_images_and_status(client):
    assert client.get('/favicon.ico').content_type == 'image/vnd.microsoft.icon'
    assert client.get('/images/missing.png').status_code == 404
    assert client.get('/status').json == {'result': 'success', 'message': 'Ok'}


def test_settings(client):
    assert client.get('/settings/').status_code == 200
    response = client.get('/api/settings')
    assert response.status_code == 200
    assert 'Themerr' in response.json


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
