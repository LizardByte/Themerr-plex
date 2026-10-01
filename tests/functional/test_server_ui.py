"""Admin-only server routes and cross-server dashboard behavior."""

# standard imports
import re
from types import SimpleNamespace
from unittest.mock import Mock

# lib imports
import pytest
from sqlalchemy.orm import Session

# local imports
from common import admin, server_ui, webapp
from plex import auth, plexapi, servers, token_store
from themerr import storage


@pytest.fixture
def client(configured, monkeypatch):
    monkeypatch.setattr(admin, 'HASH_METHOD', 'scrypt:16384:8:1')
    current = admin._save('admin', 'a long unique passphrase')
    webapp.app.config.update(TESTING=True, WTF_CSRF_ENABLED=True, SESSION_COOKIE_SECURE=False)
    monkeypatch.setattr(plexapi, 'plex_listener', Mock())
    monkeypatch.setattr(server_ui, '_refresh', Mock())
    with webapp.app.test_client() as browser:
        with browser.session_transaction() as session:
            session['admin_revision'] = current['revision']
        yield browser


def headers(client):
    page = client.get('/servers')
    token = re.search(rb'name="csrf-token" content="([^"]+)"', page.data).group(1).decode()
    return {'X-CSRFToken': token}


def save_server(identifier):
    with Session(storage.engine()) as session:
        session.add(servers.ServerRecord(id=identifier, name='Server ' + identifier,
                                         url='http://' + identifier + ':32400'))
        session.commit()


def snapshot(title, provider=None):
    item = {'rating_key': '42', 'title': title, 'type': 'movie',
            'theme': bool(provider), 'theme_provider': provider,
            'theme_status': 'complete' if provider else 'pending'}
    return {'1': {'key': 1, 'title': 'Movies', 'agent': 'tv.plex.agents.movie', 'type': 'movie',
                  'media_count': 1, 'media_percent_complete': 100 if provider else 0,
                  'collection_count': 0, 'collection_percent_complete': 0, 'collections_enabled': False,
                  'total_count': 1, 'items': [item]}}


def test_scoped_dashboard_and_playback_url_do_not_mix_identical_rating_keys(client):
    for identifier, provider in [('a', 'themerr'), ('b', 'plex')]:
        save_server(identifier)
        with storage.server_scope(identifier):
            storage.replace_dashboard(snapshot('Title ' + identifier, provider))
    with storage.server_scope('b'):
        storage.set_error(42, 'B cannot update its theme')
    libraries, _, stats = server_ui.dashboard()
    assert len(libraries) == 2 and stats['installed'] == 2 and stats['attention'] == 1
    assert libraries['a:1']['items'][0]['error'] is None
    assert libraries['b:1']['items'][0]['error'] == 'B cannot update its theme'
    page = client.get('/').data
    for identifier in ('a', 'b'):
        assert ('/api/servers/' + identifier + '/themes/42').encode() in page
        assert ('Title ' + identifier).encode() in page
    assert page.count(b'B cannot update its theme') == 1
    assert b'Outdated from ThemerrDB' in page
    assert b'B cannot update its theme' in client.get('/activity').data


def test_playback_selects_the_requested_server(client, monkeypatch):
    seen = []
    upstream = Mock(status_code=200, headers={'Content-Type': 'audio/mpeg'})
    upstream.iter_content.return_value = iter([b'audio'])
    server = Mock()
    server.fetchItem.return_value = SimpleNamespace(theme='/library/metadata/42/theme/123')
    server._session.get.return_value = upstream
    server.url.return_value = 'http://selected.example/theme'

    def setup():
        seen.append(storage.current_server_id())
        return server

    monkeypatch.setattr(plexapi, 'setup_plexapi', setup)
    response = client.get('/api/servers/b/themes/42')
    assert response.data == b'audio' and response.status_code == 200
    assert seen == ['b']
    assert storage.current_server_id() == 'default'
    response.close()


def test_discovery_and_server_settings_require_csrf(client, monkeypatch):
    discover = Mock(return_value=[{'id': 'one', 'name': 'Living room', 'connections': []}])
    monkeypatch.setattr(servers, 'discover_account', discover)
    assert client.post('/api/servers/discover', json={'source': 'account'}).status_code == 400
    response = client.post('/api/servers/discover', json={'source': 'account'}, headers=headers(client))
    assert response.status_code == 200 and response.json['servers'][0]['name'] == 'Living room'
    discover.assert_called_once()
    monkeypatch.setattr(servers, 'discover_local', Mock(side_effect=OSError('private token')))
    response = client.post('/api/servers/discover', json={'source': 'local'}, headers=headers(client))
    assert response.status_code == 502 and 'private token' not in str(response.json)
    assert client.post('/api/servers/discover', json={'source': 'invalid'}, headers=headers(client)).status_code == 400
    save_server('one')
    for path, payload in [('/api/servers', {'url': 'http://plex.example'}), ('/api/servers/one', {'enabled': False}),
                          ('/api/tasks/refresh', {'scan': True})]:
        assert client.post(path, json=payload).status_code == 400
    assert client.delete('/api/servers/one').status_code == 400


def test_add_update_remove_and_sanitized_failures(client, monkeypatch):
    add = Mock(return_value={'id': 'one', 'name': 'Plex'})
    monkeypatch.setattr(servers, 'add_server', add)
    response = client.post('/api/servers', json={'url': 'https://plex.example', 'resource_id': 'one'},
                           headers=headers(client))
    assert response.status_code == 201
    add.assert_called_once_with('https://plex.example', 'one')
    server_ui._refresh.assert_called_once()
    plexapi.plex_listener.assert_called_once()
    for error, status in [(ValueError('Invalid address.'), 400), (OSError('private key'), 500),
                          (RuntimeError('private token'), 502)]:
        add.side_effect = error
        response = client.post('/api/servers', json={'url': 'https://plex.example'}, headers=headers(client))
        assert response.status_code == status
        assert 'private' not in str(response.json)
    save_server('one')
    assert client.post('/api/servers/one', json={'enabled': False}, headers=headers(client)).status_code == 200
    assert servers.get_server('one')['enabled'] is False
    assert client.post('/api/servers/one', json={'enabled': 'false'}, headers=headers(client)).status_code == 400
    assert client.post('/api/servers/missing', json={}, headers=headers(client)).status_code == 404
    assert client.delete('/api/servers/one', headers=headers(client)).status_code == 200
    assert servers.get_server('one') is None


@pytest.mark.parametrize('payload', ['not an object', ['list'], 123, None])
def test_server_apis_reject_scalar_json(client, payload):
    response = client.post('/api/servers/discover', json=payload, headers=headers(client))
    assert response.status_code == 400
    assert response.is_json


def test_disconnecting_account_pauses_servers_and_keeps_tracking(client):
    auth.set_token('account-secret')
    save_server('one')
    token_store.save_token(servers.credential_id('one'), 'server-secret')
    with storage.server_scope('one'):
        storage.save_tracking(42, 'movie', {'youtube_theme_url': 'tracked'})
    response = client.post('/api/plex/auth/disconnect', headers=headers(client))
    assert response.status_code == 200
    assert auth.get_token() == '' and token_store.get_token(servers.credential_id('one')) == ''
    assert servers.get_server('one')['enabled'] is False
    with storage.server_scope('one'):
        assert storage.get_tracking(42)['youtube_theme_url'] == 'tracked'


def test_refresh_dispatch_and_task_status(client, configured, monkeypatch):
    from themerr import scheduled_tasks
    run = Mock()
    monkeypatch.setattr(scheduled_tasks, 'run_threaded', run)
    server_ui._refresh.return_value = SimpleNamespace(job_id='dashboard-job')
    response = client.post('/api/tasks/refresh', json={'scan': True}, headers=headers(client))
    assert response.status_code == 202
    assert response.json['job_id'] == 'dashboard-job'
    run.assert_called_once_with(target=plexapi.scheduled_update, task_name='Theme scan and queue')
    server_ui._refresh.assert_called_once()
    configured['Themerr']['BOOL_THEMERR_ENABLED'] = False
    assert client.post('/api/tasks/refresh', json={'scan': True}, headers=headers(client)).status_code == 400
    assert client.get('/api/tasks').json.keys() == {'jobs', 'queue_size'}


def test_new_pages_are_usable_without_any_server_and_have_no_background_video(client):
    for path in ('/', '/servers', '/settings/', '/activity'):
        response = client.get(path)
        assert response.status_code == 200
        assert b'<video' not in response.data
        assert b'backgroundVideo' not in response.data
        assert b'Your workspace' not in response.data or b'Themerr' in response.data
    assert b'Connect a server' in client.get('/').data
    assert b'password-form' in client.get('/settings/').data


def test_activity_includes_unresolved_ids_counted_on_overview(client):
    save_server('one')
    data = snapshot('Unresolved metadata')
    data['1']['items'][0]['theme_status'] = 'unresolved'
    with storage.server_scope('one'):
        storage.replace_dashboard(data)
    assert server_ui.dashboard()[2]['attention'] == 1
    activity = client.get('/activity').data
    assert b'Unresolved metadata' in activity
    assert b'TMDB ID unavailable. Review the item metadata in Plex.' in activity
    assert b'Outdated from ThemerrDB' not in activity
