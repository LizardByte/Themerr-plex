"""Admin-only server routes and cross-server dashboard behavior."""

# standard imports
import re
from types import SimpleNamespace
from unittest.mock import Mock

# lib imports
import pytest
from plexapi.exceptions import Unauthorized
from requests.exceptions import (ConnectionError, ConnectTimeout, JSONDecodeError, ReadTimeout, RequestException,
                                 SSLError)
from sqlalchemy.orm import Session

# local imports
from common import admin, server_ui, webapp
from common.validation import ValidationError, ValidationMessage
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
    assert len(libraries) == 2
    assert stats['installed'] == 2
    assert stats['attention'] == 1
    assert libraries['a:1']['items'][0]['error'] is None
    assert libraries['b:1']['items'][0]['error'] == 'B cannot update its theme'
    page = client.get('/').data
    for identifier in ('a', 'b'):
        assert ('/api/servers/' + identifier + '/themes/42').encode() in page
        assert ('Title ' + identifier).encode() in page
        server_url = 'https://app.plex.tv/desktop/#!/media/' + identifier + '/com.plexapp.plugins.library'
        assert f'href="{server_url}" target="_blank" rel="noopener noreferrer"'.encode() in page
        assert f'href="{server_url}?source=1" target="_blank" rel="noopener noreferrer"'.encode() in page
    assert page.count(b'B cannot update its theme') == 1
    assert b'Outdated from ThemerrDB' in page
    assert b'B cannot update its theme' in client.get('/activity').data


def test_publication_api_requires_login_and_returns_cached_status(client, monkeypatch):
    from themerr import github_status
    status = {'updated_at': '2026-10-02T12:00:00+00:00', 'next_check': 12345, 'stale': False}
    lookup = Mock(return_value=status)
    monkeypatch.setattr(github_status, 'publication_status', lookup)
    with webapp.app.test_client() as anonymous:
        assert anonymous.get('/api/themerrdb').status_code == 401
    lookup.assert_not_called()
    result = client.get('/api/themerrdb')
    assert result.status_code == 200
    assert result.json == status
    assert result.headers['Cache-Control'] == 'no-store'
    lookup.assert_called_once()


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
    assert response.data == b'audio'
    assert response.status_code == 200
    assert seen == ['b']
    assert storage.current_server_id() == 'default'
    response.close()


def test_discovery_and_server_settings_require_csrf(client, monkeypatch):
    discover = Mock(return_value=[{'id': 'one', 'name': 'Living room', 'connections': []}])
    monkeypatch.setattr(servers, 'discover_account', discover)
    assert client.post('/api/servers/discover', json={'source': 'account'}).status_code == 400
    response = client.post('/api/servers/discover', json={'source': 'account'}, headers=headers(client))
    assert response.status_code == 200
    assert response.json['servers'][0]['name'] == 'Living room'
    discover.assert_called_once()
    monkeypatch.setattr(servers, 'discover_local', Mock(side_effect=OSError('private token')))
    response = client.post('/api/servers/discover', json={'source': 'local'}, headers=headers(client))
    assert response.status_code == 502
    assert 'private token' not in str(response.json)
    assert client.post('/api/servers/discover', json={'source': 'invalid'}, headers=headers(client)).status_code == 400
    save_server('one')
    for path, payload in [('/api/servers', {'url': 'http://plex.example'}), ('/api/servers/one', {'enabled': False}),
                          ('/api/tasks/refresh', {'scan': True})]:
        assert client.post(path, json=payload).status_code == 400
    assert client.delete('/api/servers/one').status_code == 400


def test_add_update_and_remove_server(client, monkeypatch):
    add = Mock(return_value={'id': 'one', 'name': 'Plex'})
    monkeypatch.setattr(servers, 'add_server', add)
    response = client.post('/api/servers', json={'url': 'https://plex.example', 'resource_id': 'one'},
                           headers=headers(client))
    assert response.status_code == 201
    add.assert_called_once_with('https://plex.example', 'one')
    server_ui._refresh.assert_called_once()
    plexapi.plex_listener.assert_called_once()
    save_server('one')
    assert client.post('/api/servers/one', json={'enabled': False}, headers=headers(client)).status_code == 200
    assert servers.get_server('one')['enabled'] is False
    assert client.post('/api/servers/one', json={'enabled': 'false'}, headers=headers(client)).status_code == 400
    assert client.post('/api/servers/missing', json={}, headers=headers(client)).status_code == 404
    assert client.delete('/api/servers/one', headers=headers(client)).status_code == 200
    assert servers.get_server('one') is None


@pytest.mark.parametrize(('error', 'status', 'reason'), [
    (ValidationError(ValidationMessage.PLEX_ADDRESS_INVALID), 400, 'valid Plex server address'),
    (ValueError('private token'), 502, 'Could not connect'),
    (token_store.TokenStorageError('private key'), 500, 'credential store'),
    (ConnectTimeout('private token'), 502, 'timed out'),
    (ReadTimeout('private token'), 502, 'timed out'),
    (SSLError('private token'), 502, 'server certificate'),
    (ConnectionError('private token'), 502, 'hostname, port, and network access'),
    (Unauthorized('private token'), 502, 'denied access'),
    (RequestException('private token'), 502, 'invalid response'),
    (JSONDecodeError('private token', 'private body', 0), 502, 'invalid response'),
    (OSError('private key'), 502, 'Could not connect'),
    (RuntimeError('private token'), 502, 'Could not connect'),
])
def test_connect_failures_distinguish_network_from_credential_store(client, monkeypatch, error, status, reason):
    monkeypatch.setattr(servers, 'add_server', Mock(side_effect=error))
    log = Mock()
    monkeypatch.setattr(server_ui, 'log', log)
    response = client.post('/api/servers', json={'url': 'https://plex.example'}, headers=headers(client))
    assert response.status_code == status
    assert reason in response.json['message']
    assert 'private' not in str(response.json)
    assert 'private' not in str(log.warning.call_args)
    if not isinstance(error, token_store.TokenStorageError):
        assert 'credential store' not in response.json['message']
    server_ui._refresh.assert_not_called()
    plexapi.plex_listener.assert_not_called()


@pytest.mark.parametrize('method, operation', [('POST', 'update_server'), ('DELETE', 'remove_server')])
@pytest.mark.parametrize('failure', [ValueError, RuntimeError])
def test_server_edit_unexpected_failure_is_not_exposed(client, monkeypatch, method, operation, failure):
    save_server('one')
    monkeypatch.setattr(servers, operation, Mock(side_effect=failure('private token and database details')))
    log = Mock()
    monkeypatch.setattr(server_ui, 'log', log)
    response = client.open('/api/servers/one', method=method, json={'enabled': False}, headers=headers(client))
    assert response.status_code == 500
    assert response.json == {'message': 'Could not update this Plex server. Check its connection and settings.'}
    assert 'private' not in str(log.warning.call_args)
    assert servers.get_server('one') is not None
    plexapi.plex_listener.assert_not_called()


@pytest.mark.parametrize('address, message', [
    ('http://[invalid', 'Enter a valid Plex server address.'),
    ('http://plex.example:private-port', 'Invalid server port.'),
    ('http://plex.example:99999', 'Invalid server port.'),
])
def test_malformed_server_address_returns_public_validation(client, address, message):
    response = client.post('/api/servers', json={'url': address}, headers=headers(client))
    assert response.status_code == 400
    assert response.json == {'message': message}
    server_ui._refresh.assert_not_called()
    plexapi.plex_listener.assert_not_called()


def test_removing_server_reports_credential_store_failure_and_retains_connection(client, monkeypatch):
    save_server('one')
    monkeypatch.setattr(token_store, 'delete_token', Mock(side_effect=token_store.TokenStorageError('private key')))
    response = client.delete('/api/servers/one', headers=headers(client))
    assert response.status_code == 500
    assert response.json['message'] == 'Could not update the secure credential store.'
    assert servers.get_server('one') is not None


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
    assert auth.get_token() == ''
    assert token_store.get_token(servers.credential_id('one')) == ''
    assert servers.get_server('one')['enabled'] is False
    with storage.server_scope('one'):
        assert storage.get_tracking(42)['youtube_theme_url'] == 'tracked'


def test_refresh_dispatch_and_task_status(client, configured, monkeypatch):
    from themerr import scheduled_tasks
    run = Mock()
    monkeypatch.setattr(scheduled_tasks, 'run_threaded', run)
    monkeypatch.setattr(server_ui, '_refresh', Mock(return_value=SimpleNamespace(job_id='dashboard-job')))
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


@pytest.mark.parametrize(('kind', 'database_id', 'source_database', 'source_id', 'url'), [
    ('movie', '550988', None, None, 'https://www.themoviedb.org/movie/550988'),
    ('show', '1407', None, None, 'https://www.themoviedb.org/tv/1407'),
    ('collection', '10', None, None, 'https://www.themoviedb.org/collection/10'),
    ('movie', None, 'imdb', 'tt0497329', 'https://www.imdb.com/title/tt0497329/'),
    ('show', None, 'thetvdb', '71862', 'https://thetvdb.com/dereferrer/series/71862'),
    ('movie', 'bad/id', None, None, None),
])
def test_provider_links_and_scoped_plex_links(client, kind, database_id, source_database, source_id, url):
    save_server('a')
    data = snapshot('Linked title')
    data['1']['items'][0].update(
        type=kind, database_id=database_id, source_database=source_database, source_id=source_id,
    )
    with storage.server_scope('a'):
        storage.replace_dashboard(data)
    rendered = client.get('/').data
    assert b'https://app.plex.tv/desktop/#!/server/a/details?key=%2Flibrary%2Fmetadata%2F42' in rendered
    link = re.search(rb'<a class="plex-item-link"[^>]*>.*?</a>', rendered).group()
    assert b'target="_blank" rel="noopener noreferrer" title="Open in Plex: Linked title"' in link
    assert b'Plex ID: 42' in link
    if url:
        assert ('href="' + url + '" target="_blank" rel="noopener noreferrer"').encode() in rendered
    else:
        assert b'metadata-link' not in rendered


@pytest.mark.parametrize(('reason', 'action', 'visible'), [
    (None, 'edit', False), ('Video unavailable', 'edit', True),
    ('Video unavailable in your country', 'edit', False), ('Theme upload failed', 'edit', False),
    (None, 'add', True),
])
def test_contribution_actions_reflect_video_issues(client, reason, action, visible):
    save_server('a')
    data = snapshot('Theme row', 'themerr')
    data['1']['items'][0].update(issue_action=action, issue_url='https://github.com/LizardByte/ThemerrDB/issues/new')
    with storage.server_scope('a'):
        storage.replace_dashboard(data)
        storage.set_error(42, reason)
    rendered = client.get('/').data
    assert (b'class="contribute-link"' in rendered) is visible
    assert b'class="media-controls"' in rendered
    assert b'title="Movie" aria-hidden="true"' in rendered
    assert b'data-lucide="film"' in rendered
    assert b'data-lucide="play"' in rendered
