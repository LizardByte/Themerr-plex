"""Embedded MCP protocol, scoped credentials, and server-isolated theme workflows."""

# standard imports
import json
import logging
from types import SimpleNamespace
from unittest.mock import Mock

# lib imports
from fastapi.testclient import TestClient
from itsdangerous import URLSafeTimedSerializer
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

# local imports
from common import admin, logger, log_viewer, mcp_auth, webapp
from jellyfin import repository
from jellyfin import servers as jellyfin_servers
from media_servers import processing
from plex import servers
from tests.http_helpers import get_session, set_session
from themerr import mcp_tools, storage, themerr_db

PASSWORD = 'a unique test password'
JELLYFIN = 'jellyfin:second'


def _item(item_id, title='Example', theme=False, status='pending'):
    return {
        'rating_key': item_id,
        'title': title,
        'type': 'movie',
        'year': 2020,
        'theme': theme,
        'theme_status': status,
        'theme_provider': 'themerr' if theme else None,
        'database': 'tmdb',
        'database_id': '123',
    }


def _library(key, items):
    return {
        'key': key,
        'title': f'Library {key}',
        'agent': 'tv.plex.agents.movie',
        'type': 'movie',
        'media_count': len(items),
        'media_percent_complete': 0,
        'collection_count': 0,
        'collection_percent_complete': 0,
        'collections_enabled': False,
        'total_count': len(items),
        'items': items,
    }


@pytest.fixture
def mcp_client(configured, monkeypatch):
    monkeypatch.setattr(admin, 'HASH_METHOD', 'scrypt:16384:8:1')
    monkeypatch.delenv('THEMERR_MCP_ALLOWED_HOSTS', raising=False)
    monkeypatch.setattr(processing, 'q', processing._WorkQueue())
    monkeypatch.setattr(processing, '_active_items', set())
    configured['Themerr']['BOOL_THEMERR_ENABLED'] = True
    current = admin._save('admin', PASSWORD)
    with Session(storage.engine()) as database:
        database.add(servers.ServerRecord(
            id='first', name='Plex', url='http://plex.example', enabled=True,
            data_directory='C:/private/media', last_refresh='2026-10-09T12:00:00Z',
        ))
        database.add(jellyfin_servers.ServerRecord(
            id=JELLYFIN, name='Jellyfin', url='http://jellyfin.example', version='10.11.0', enabled=True,
        ))
        database.commit()
    with storage.server_scope('first'):
        storage.replace_dashboard({
            '1': _library('1', [
                _item('42', 'Dune', True, 'complete'),
                _item('43', 'Dune Part Two'),
                _item('44', '100% literal', False, 'failed'),
            ]),
            '2': _library('2', [_item('42', 'Dune', True, 'complete')]),
        })
        storage.set_error('44', 'YouTube video is unavailable')
        storage.save_tracking('42', 'movie', {
            'youtube_theme_url': 'https://www.youtube.com/watch?v=example',
            'uploaded_theme_key': '/private/metadata/theme',
            'audio_codec': 'mp3',
        })
    with storage.server_scope(JELLYFIN):
        storage.replace_dashboard({'1': _library('1', [_item('42', 'Other server')])})
    read_token = mcp_auth.create_token('read')
    process_token = mcp_auth.create_token('process')
    with TestClient(webapp.create_app(https_only=False), base_url='http://localhost',
                    follow_redirects=False) as client:
        client.read_token = read_token
        client.process_token = process_token
        client.admin_revision = current['revision']
        yield client


@pytest.fixture
def themerrdb_index(monkeypatch):
    monkeypatch.setattr(themerr_db, 'database_cache', {
        'movies': {
            'themoviedb': {'123'},
            'imdb': {'tt123'},
        },
        'tv_shows': {'themoviedb': {'456'}},
        'movie_collections': {'themoviedb': {'645'}},
    })
    monkeypatch.setattr(themerr_db, 'lookup_cache', {})
    monkeypatch.setattr(themerr_db, 'last_cache_update', 10000)
    clock = Mock(return_value=10000)
    monkeypatch.setattr(themerr_db, 'time', SimpleNamespace(time=clock))
    request = Mock(side_effect=AssertionError('No network expected for a fresh index'))
    monkeypatch.setattr(themerr_db.helpers, 'json_get', request)
    return (
        request,
        clock,
    )


def _rpc(client, method, params=None, token=None, **kwargs):
    headers = {
        'Authorization': f'Bearer {token or client.read_token}',
        'Accept': 'application/json, text/event-stream',
        'MCP-Protocol-Version': '2025-11-25',
    }
    headers.update(kwargs.pop('headers', {}))
    return client.post('/mcp', json={
        'jsonrpc': '2.0',
        'id': 1,
        'method': method,
        'params': params or {},
    }, headers=headers, **kwargs)


def _call(client, name, arguments=None, token=None):
    response = _rpc(client, 'tools/call', {
        'name': name,
        'arguments': arguments or {},
    }, token)
    assert response.status_code == 200, response.text
    return response.json()['result']


def _data(client, name, arguments=None, token=None):
    result = _call(client, name, arguments, token)
    assert not result.get('isError'), result
    return result['structuredContent']


def test_protocol_initialization_and_tool_discovery(mcp_client):
    response = _rpc(mcp_client, 'initialize', {
        'protocolVersion': '2025-11-25',
        'capabilities': {},
        'clientInfo': {
            'name': 'test',
            'version': '1',
        },
    })
    assert response.status_code == 200
    assert response.json()['result']['serverInfo']['name'] == 'Themerr'
    tools = _rpc(mcp_client, 'tools/list').json()['result']['tools']
    by_name = {tool['name']: tool for tool in tools}
    assert set(by_name) == {
        'list_servers',
        'list_libraries',
        'search_items',
        'get_theme_coverage',
        'inspect_theme',
        'check_themerrdb',
        'get_activity',
        'get_logs',
        'refresh_libraries',
        'retry_items',
    }
    assert all('ctx' not in tool['inputSchema']['properties'] for tool in tools)
    assert by_name['search_items']['annotations']['readOnlyHint'] is True
    assert by_name['check_themerrdb']['annotations']['readOnlyHint'] is True
    assert by_name['check_themerrdb']['annotations']['destructiveHint'] is False
    assert by_name['check_themerrdb']['annotations']['openWorldHint'] is True
    assert by_name['retry_items']['annotations']['readOnlyHint'] is False
    assert by_name['retry_items']['annotations']['destructiveHint'] is True
    assert 'Mcp-Session-Id' not in response.headers
    assert response.headers['Cache-Control'] == 'no-store'


@pytest.mark.parametrize('authorization', [
    '',
    'Bearer invalid',
    'Basic invalid',
    f'Bearer tmcp_{"x" * 43}',
])
def test_browser_session_does_not_authorize_mcp(mcp_client, authorization):
    set_session(mcp_client, {'admin_revision': mcp_client.admin_revision})
    response = mcp_client.post('/mcp', json={}, headers={'Authorization': authorization})
    assert response.status_code == 401
    assert response.json() == {'message': 'A valid MCP bearer token is required.'}
    assert response.headers['WWW-Authenticate'] == 'Bearer realm="Themerr MCP"'
    assert response.headers['Cache-Control'] == 'no-store'


def test_mcp_token_cannot_authorize_browser_api(mcp_client):
    response = mcp_client.get('/api/settings', headers={'Authorization': f'Bearer {mcp_client.process_token}'})
    assert response.status_code == 401


def _browser_headers(client):
    set_session(client, {'admin_revision': client.admin_revision})
    client.get('/settings/')
    serializer = URLSafeTimedSerializer(client.app.state.secret_key, salt='csrf-token')
    return {'X-CSRFToken': serializer.dumps(get_session(client)['csrf_token'])}


def test_web_ui_creates_lists_and_revokes_individual_tokens(mcp_client):
    headers = _browser_headers(mcp_client)
    page = mcp_client.get('/settings/')
    assert 'id="mcp-token-form"' in page.text
    assert '<output id="mcp-endpoint"' in page.text
    assert '<output id="mcp-new-token"' in page.text
    for field_id in (
        'mcp-endpoint',
        'mcp-new-token',
    ):
        field = page.text.split(f'<output id="{field_id}"', 1)[1].split('>', 1)[0]
        assert 'tabindex="-1"' in field
    assert 'id="mcp-copy-endpoint"' in page.text
    assert 'id="mcp-toggle-token"' in page.text
    assert 'Example prompts' in page.text
    assert 'Show movies with failed themes on my Jellyfin server.' in page.text
    assert 'Check whether movie TMDB ID 123 is in ThemerrDB.' in page.text
    assert 'http://localhost/mcp' in page.text
    assert mcp_client.read_token not in page.text
    payload = {
        'name': 'My assistant',
        'scope': 'read',
    }
    assert mcp_client.post('/api/mcp/tokens', json=payload).status_code == 400
    created = mcp_client.post('/api/mcp/tokens', json=payload, headers=headers)
    assert created.status_code == 201
    token = created.json()['token']
    listed = mcp_client.get('/api/mcp/tokens').json()['tokens']
    named = next(row for row in listed if row['name'] == 'My assistant')
    assert named['scope'] == 'read'
    assert named['active'] is True
    assert token not in json.dumps(listed)
    assert token not in mcp_client.get('/settings/').text
    assert _rpc(mcp_client, 'tools/list', token=token).status_code == 200
    path = f'/api/mcp/tokens/{named["id"]}'
    assert mcp_client.delete(path).status_code == 400
    assert mcp_client.delete(path, headers=headers).status_code == 200
    assert _rpc(mcp_client, 'tools/list', token=token).status_code == 401
    assert _rpc(mcp_client, 'tools/list').status_code == 200
    assert mcp_client.delete(path, headers=headers).status_code == 404


@pytest.mark.parametrize('enabled', [
    False,
    True,
])
def test_companion_http_mcp_is_opt_in_and_exposes_no_admin_routes(mcp_client, configured, enabled):
    _browser_headers(mcp_client)
    configured['Network']['MCP_HTTP'] = enabled
    with TestClient(repository.create_app(), base_url='http://localhost:9495') as client:
        client.read_token = mcp_client.read_token
        client.process_token = mcp_client.process_token
        client.cookies.update(mcp_client.cookies)
        for path in (
            '/login',
            '/setup',
            '/settings/',
            '/api/settings',
            '/api/mcp/tokens',
            '/api/openapi.json',
            '/mcp/other',
        ):
            assert client.get(path).status_code == 404
            assert client.post(path, json={}).status_code == 404
        assert _rpc(client, 'tools/list').status_code == (200 if enabled else 404)
        assert _rpc(client, 'tools/list', headers={'Authorization': ''}).status_code == (401 if enabled else 404)
        if enabled:
            initialized = _rpc(client, 'initialize', {
                'protocolVersion': '2025-11-25',
                'capabilities': {},
                'clientInfo': {
                    'name': 'http-test',
                    'version': '1',
                },
            }).json()['result']
            assert initialized['serverInfo']['name'] == 'Themerr'
            assert _data(client, 'get_theme_coverage')['total'] == 4
            denied = _call(client, 'refresh_libraries')
            assert denied['isError'] is True
            assert 'process token' in denied['content'][0]['text']
            assert _rpc(client, 'tools/list', headers={'Host': 'attacker.example'}).status_code == 421
            assert _rpc(client, 'tools/list', headers={'Origin': 'http://attacker.example'}).status_code == 403
            oversized = client.post('/mcp', content=b'x' * (64 * 1024 + 1), headers={
                'Authorization': f'Bearer {client.read_token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json, text/event-stream',
            })
            assert oversized.status_code == 413
            assert oversized.headers['Cache-Control'] == 'no-store'
            assert _rpc(mcp_client, 'tools/list').status_code == 200


@pytest.mark.parametrize('password_changed', [
    False,
    True,
])
def test_companion_http_tokens_follow_revocation_and_password_changes(mcp_client, configured, password_changed):
    configured['Network']['MCP_HTTP'] = True
    with TestClient(repository.create_app(), base_url='http://localhost:9495') as client:
        client.read_token = mcp_client.read_token
        assert _rpc(client, 'tools/list').status_code == 200
        if password_changed:
            admin._save('admin', f'{PASSWORD} changed')
        else:
            mcp_auth.revoke_tokens()
        assert _rpc(client, 'tools/list').status_code == 401
        assert _rpc(mcp_client, 'tools/list').status_code == 401


@pytest.mark.parametrize('port', [
    None,
    9495,
    20495,
])
def test_settings_show_only_the_active_mcp_http_endpoint(mcp_client, monkeypatch, port):
    _browser_headers(mcp_client)
    monkeypatch.setattr(repository, 'mcp_http_port', lambda: port)
    page = mcp_client.get('/settings/').text
    assert page.count('id="Network-MCP_HTTP"') == 1
    field = page.split('id="Network-MCP_HTTP"', 1)[1].split('>', 1)[0]
    assert 'form="configForm"' in field
    endpoint = f'http://localhost:{port}/mcp' if port is not None else 'http://localhost/mcp'
    assert f'tabindex="-1">{endpoint}</output>' in page


def test_mcp_http_option_is_saved_through_the_authenticated_settings_api(mcp_client, configured):
    headers = _browser_headers(mcp_client)
    assert configured['Network']['MCP_HTTP'] is False
    for enabled in (
        'true',
        'false',
    ):
        response = mcp_client.post('/api/settings', data={'Network|MCP_HTTP': enabled}, headers=headers)
        assert response.status_code == 200
        assert configured['Network']['MCP_HTTP'] is (enabled == 'true')


def test_web_token_management_requires_browser_authentication(mcp_client):
    for method, path in (
        (
            'get',
            '/api/mcp/tokens',
        ),
        (
            'post',
            '/api/mcp/tokens',
        ),
        (
            'delete',
            '/api/mcp/tokens',
        ),
        (
            'delete',
            '/api/mcp/tokens/unknown',
        ),
    ):
        response = getattr(mcp_client, method)(path, headers={'Authorization': f'Bearer {mcp_client.process_token}'})
        assert response.status_code == 401


@pytest.mark.parametrize('payload', [
    {
        'name': 'Client',
        'scope': 'admin',
    },
    {
        'name': '',
        'scope': 'read',
    },
    {
        'name': 'x' * 65,
        'scope': 'read',
    },
    {
        'name': False,
        'scope': 'read',
    },
    {
        'name': 'Client',
        'scope': ['read'],
    },
    {'scope': 'read'},
    {
        'name': 'Client',
        'scope': 'read',
        'extra': True,
    },
    [],
])
def test_web_token_creation_validates_names_and_scopes(mcp_client, payload):
    headers = _browser_headers(mcp_client)
    response = mcp_client.post('/api/mcp/tokens', json=payload, headers=headers)
    assert response.status_code == 400
    assert len(mcp_auth.list_tokens()) == 2


def test_web_ui_revokes_all_tokens_with_csrf(mcp_client):
    headers = _browser_headers(mcp_client)
    assert mcp_client.delete('/api/mcp/tokens').status_code == 400
    response = mcp_client.delete('/api/mcp/tokens', headers=headers)
    assert response.status_code == 200
    assert response.json()['tokens'] == []
    assert _rpc(mcp_client, 'tools/list').status_code == 401


def test_only_digests_are_persisted_and_revocation_takes_effect(mcp_client):
    with Session(storage.engine()) as database:
        values = database.scalars(select(storage.AppSetting.value)).all()
    assert mcp_client.read_token not in json.dumps(values)
    assert mcp_client.process_token not in json.dumps(values)
    assert _data(mcp_client, 'get_activity')['uploads_idle'] is True
    mcp_auth.revoke_tokens()
    assert _rpc(mcp_client, 'tools/list').status_code == 401
    assert _rpc(mcp_client, 'tools/list', token=mcp_client.process_token).status_code == 401
    assert admin.account()['revision'] == mcp_client.admin_revision


def test_password_change_revokes_tokens_and_new_tokens_work(mcp_client):
    admin.reset_password('another unique test password')
    assert _rpc(mcp_client, 'tools/list').status_code == 401
    assert _rpc(mcp_client, 'tools/list', token=mcp_client.process_token).status_code == 401
    assert _rpc(mcp_client, 'tools/list', token=mcp_auth.create_token('read')).status_code == 200


def test_tokens_require_admin_setup_and_a_known_scope(configured):
    with pytest.raises(ValueError, match='admin account'):
        mcp_auth.create_token('read')
    with pytest.raises(ValueError, match='read or process'):
        mcp_auth.create_token('admin')


@pytest.mark.parametrize('name,arguments', [
    (
        'refresh_libraries',
        {},
    ),
    (
        'retry_items',
        {
            'server_id': 'first',
            'item_ids': ['43'],
        },
    ),
])
def test_read_scope_cannot_dispatch_work(mcp_client, monkeypatch, name, arguments):
    refresh = Mock()
    enqueue = Mock()
    monkeypatch.setattr(mcp_tools.scheduled_tasks, 'run_threaded', refresh)
    monkeypatch.setattr(processing, 'enqueue', enqueue)
    result = _call(mcp_client, name, arguments)
    assert result['isError'] is True
    assert 'process token' in result['content'][0]['text']
    refresh.assert_not_called()
    enqueue.assert_not_called()


def test_server_and_library_discovery_are_cached_and_paginated(mcp_client, monkeypatch):
    monkeypatch.setattr(servers, 'connect', Mock(side_effect=AssertionError('No network expected')))
    monkeypatch.setattr(jellyfin_servers, 'client', Mock(side_effect=AssertionError('No network expected')))
    first = _data(mcp_client, 'list_servers', {'limit': 1})
    assert first['next_offset'] == 1
    assert len(first['servers']) == 1
    all_servers = _data(mcp_client, 'list_servers')['servers']
    assert {row['server_id'] for row in all_servers} == {
        'first',
        JELLYFIN,
    }
    assert 'data_directory' not in all_servers[0]
    assert '/private/media' not in json.dumps(all_servers)
    page = _data(mcp_client, 'list_libraries', {
        'server_id': 'first',
        'limit': 1,
    })
    assert page['libraries'][0]['library_id'] == '1'
    assert page['cached'] is True
    assert page['next_offset'] == 1
    assert page['snapshots'][0]['last_refresh'] == '2026-10-09T12:00:00Z'
    page = _data(mcp_client, 'list_libraries', {
        'server_id': 'first',
        'limit': 1,
        'offset': 1,
    })
    assert page['libraries'][0]['library_id'] == '2'
    assert page['next_offset'] is None


def test_search_filters_pagination_and_literal_matching(mcp_client):
    args = {
        'server_id': 'first',
        'query': 'dUnE',
        'limit': 1,
    }
    first = _data(mcp_client, 'search_items', args)
    assert first['items'][0]['item_id'] == '42'
    assert first['next_offset'] == 1
    second = _data(mcp_client, 'search_items', {
        **args,
        'offset': 1,
    })
    assert second['items'][0]['library_id'] != first['items'][0]['library_id']
    found = _data(mcp_client, 'search_items', {
        'server_id': 'first',
        'library_id': '1',
        'status': 'complete',
        'media_type': 'movie',
        'provider': 'themerr',
        'year': 2020,
    })
    assert [row['item_id'] for row in found['items']] == ['42']
    assert _data(mcp_client, 'search_items', {'query': '%'})['items'][0]['item_id'] == '44'
    assert not _data(mcp_client, 'search_items', {'year': 2021})['items']
    other = _data(mcp_client, 'search_items', {'server_id': JELLYFIN})
    assert [row['title'] for row in other['items']] == ['Other server']


@pytest.mark.parametrize('name,arguments', [
    (
        'list_servers',
        {'limit': 201},
    ),
    (
        'search_items',
        {'offset': -1},
    ),
    (
        'search_items',
        {'status': 'bad'},
    ),
    (
        'search_items',
        {'media_type': 'bad'},
    ),
    (
        'search_items',
        {'query': 'x' * 257},
    ),
    (
        'search_items',
        {'library_id': '1'},
    ),
    (
        'list_libraries',
        {'server_id': 'missing'},
    ),
    (
        'get_theme_coverage',
        {
            'server_id': 'first',
            'library_id': '../missing',
        },
    ),
    (
        'get_logs',
        {'source': '../themerr.log'},
    ),
    (
        'get_logs',
        {'cursor': -1},
    ),
    (
        'get_logs',
        {'level': 'bad'},
    ),
    (
        'retry_items',
        {
            'server_id': 'first',
            'item_ids': [],
        },
    ),
    (
        'retry_items',
        {
            'server_id': 'first',
            'item_ids': ['42'] * 101,
        },
    ),
])
def test_invalid_arguments_are_tool_errors(mcp_client, name, arguments):
    result = _call(mcp_client, name, arguments, mcp_client.process_token)
    assert result['isError'] is True


def test_coverage_deduplicates_memberships_but_preserves_server_scope(mcp_client):
    data = _data(mcp_client, 'get_theme_coverage')
    assert data['total'] == 4
    assert data['installed'] == 1
    assert data['coverage_percent'] == 25
    assert data['statuses'] == {
        'complete': 1,
        'pending': 2,
        'failed': 1,
    }
    scoped = _data(mcp_client, 'get_theme_coverage', {
        'server_id': 'first',
        'library_id': '2',
    })
    assert scoped['total'] == scoped['installed'] == 1
    assert scoped['coverage_percent'] == 100


def test_inspection_is_server_scoped_and_omits_private_upload_paths(mcp_client):
    data = _data(mcp_client, 'inspect_theme', {
        'server_id': 'first',
        'item_id': '42',
    })
    assert data['title'] == 'Dune'
    assert data['tracking']['audio_codec'] == 'mp3'
    assert 'uploaded_theme_key' not in data['tracking']
    assert '/private/metadata' not in json.dumps(data)
    other = _data(mcp_client, 'inspect_theme', {
        'server_id': JELLYFIN,
        'item_id': '42',
    })
    assert other['title'] == 'Other server'
    assert other['tracking'] == {}
    failed = _data(mcp_client, 'inspect_theme', {
        'server_id': 'first',
        'item_id': '44',
    })
    assert failed['error'] == 'YouTube video is unavailable'
    assert _call(mcp_client, 'inspect_theme', {
        'server_id': 'first',
        'item_id': '../missing',
    })['isError'] is True


@pytest.mark.parametrize('media_type,database,database_id,database_type', [
    (
        'movie',
        'themoviedb',
        '123',
        'movies',
    ),
    (
        'movie',
        'imdb',
        'tt123',
        'movies',
    ),
    (
        'show',
        'themoviedb',
        '456',
        'tv_shows',
    ),
    (
        'collection',
        'themoviedb',
        '645',
        'movie_collections',
    ),
])
def test_themerrdb_lookup_distinguishes_present_and_absent_ids(
        mcp_client, themerrdb_index, monkeypatch, media_type, database, database_id, database_type):
    monkeypatch.setattr(mcp_tools, 'get_backend', Mock(side_effect=AssertionError('No media server expected')))
    arguments = {
        'media_type': media_type,
        'database': database,
        'database_id': database_id,
    }
    found = _data(mcp_client, 'check_themerrdb', arguments)
    assert found == {
        **arguments,
        'database_type': database_type,
        'exists': True,
        'cached': True,
        'last_refresh': '1970-01-01T02:46:40+00:00',
    }
    missing = _data(mcp_client, 'check_themerrdb', {
        **arguments,
        'database_id': 'tt999' if database == 'imdb' else '999',
    }, token=mcp_client.process_token)
    assert missing['exists'] is False
    themerrdb_index[0].assert_not_called()


def test_themerrdb_lookup_defaults_to_tmdb_and_preserves_media_categories(mcp_client, themerrdb_index):
    movie = _data(mcp_client, 'check_themerrdb', {
        'media_type': 'movie',
        'database_id': '123',
    })
    assert movie['exists'] is True
    assert movie['database'] == 'themoviedb'
    show = _data(mcp_client, 'check_themerrdb', {
        'media_type': 'show',
        'database_id': '123',
    })
    assert show['exists'] is False


@pytest.mark.parametrize('arguments', [
    {},
    {
        'media_type': 'episode',
        'database_id': '123',
    },
    {
        'media_type': 'movie',
        'database': 'tvdb',
        'database_id': '123',
    },
    {
        'media_type': 'show',
        'database': 'imdb',
        'database_id': 'tt123',
    },
    {
        'media_type': 'collection',
        'database': 'imdb',
        'database_id': 'tt123',
    },
    {
        'media_type': 'movie',
        'database': 'imdb',
        'database_id': '123',
    },
    {
        'media_type': 'movie',
        'database': 'imdb',
        'database_id': 'tt',
    },
    {
        'media_type': 'movie',
        'database_id': '../123',
    },
    {
        'media_type': 'movie',
        'database_id': 'https://example.com/123',
    },
    {
        'media_type': 'movie',
        'database_id': '\u0661\u0662\u0663',
    },
    {
        'media_type': 'movie',
        'database_id': '',
    },
    {
        'media_type': 'movie',
        'database_id': '1' * 257,
    },
])
def test_themerrdb_lookup_rejects_invalid_ids_before_refreshing(mcp_client, themerrdb_index, arguments):
    themerrdb_index[1].return_value = 13601
    assert _call(mcp_client, 'check_themerrdb', arguments)['isError'] is True
    themerrdb_index[0].assert_not_called()


@pytest.mark.parametrize('initialized', [
    False,
    True,
])
def test_themerrdb_lookup_refreshes_an_expired_index_once(mcp_client, themerrdb_index, initialized):
    request, clock = themerrdb_index
    clock.return_value = 13601
    if not initialized:
        themerr_db.database_cache.clear()
        themerr_db.last_cache_update = 0

    def index(**kwargs):
        if kwargs['url'].endswith('/pages.json'):
            return {'pages': 1}
        return [{
            'id': 789,
            'imdb_id': 'tt789',
            'title': 'New item',
        }]

    request.side_effect = index
    arguments = {
        'media_type': 'movie',
        'database_id': '789',
    }
    refreshed = _data(mcp_client, 'check_themerrdb', arguments)
    assert refreshed['exists'] is True
    assert refreshed['last_refresh'] == '1970-01-01T03:46:41+00:00'
    assert request.call_count == 6
    assert _data(mcp_client, 'check_themerrdb', arguments)['exists'] is True
    assert request.call_count == 6


def test_themerrdb_lookup_does_not_report_a_failed_index_as_absent(mcp_client, themerrdb_index):
    request, clock = themerrdb_index
    clock.return_value = 13601
    request.side_effect = RuntimeError('private network error')
    arguments = {
        'media_type': 'movie',
        'database_id': '123',
    }
    for _ in range(2):
        result = _call(mcp_client, 'check_themerrdb', arguments)
        assert result['isError'] is True
        assert 'ThemerrDB index is unavailable' in result['content'][0]['text']
        assert 'private network error' not in json.dumps(result)
    assert request.call_count == 3


def test_themerrdb_lookup_reports_absent_from_a_successfully_empty_index(mcp_client, themerrdb_index):
    request, clock = themerrdb_index
    clock.return_value = 13601
    request.side_effect = None
    request.return_value = {'pages': 0}
    result = _data(mcp_client, 'check_themerrdb', {
        'media_type': 'movie',
        'database_id': '123',
    })
    assert result['exists'] is False
    assert request.call_count == 3


def test_process_refresh_only_dispatches_metadata_refresh(mcp_client, monkeypatch):
    dispatch = Mock(return_value=SimpleNamespace(job_id='refresh-id'))
    scan = Mock()
    monkeypatch.setattr(mcp_tools.scheduled_tasks, 'run_threaded', dispatch)
    monkeypatch.setattr(processing, 'scheduled_update', scan)
    data = _data(mcp_client, 'refresh_libraries', token=mcp_client.process_token)
    assert data == {
        'job_id': 'refresh-id',
        'status': 'dispatched',
    }
    dispatch.assert_called_once_with(target=mcp_tools.cache.cache_data, task_name='Dashboard refresh')
    scan.assert_not_called()


def test_retry_deduplicates_queued_and_active_work_and_tracks_uploads(mcp_client):
    data = _data(mcp_client, 'retry_items', {
        'server_id': 'first',
        'item_ids': [
            '43',
            '43',
        ],
    }, mcp_client.process_token)
    assert data['queued_item_ids'] == ['43']
    assert processing.q.queue[0] == (
        'first',
        '43',
    )
    activity = _data(mcp_client, 'get_activity')
    assert activity['queued_items'] == 1
    assert activity['active_items'] == 0
    assert activity['uploads_idle'] is False
    assert processing.q.get_nowait() == (
        'first',
        '43',
    )
    data = _data(mcp_client, 'retry_items', {
        'server_id': 'first',
        'item_ids': ['43'],
    }, mcp_client.process_token)
    assert data['queued_item_ids'] == []
    assert data['already_queued_or_active_item_ids'] == ['43']
    activity = _data(mcp_client, 'get_activity')
    assert activity['queued_items'] == 0
    assert activity['active_items'] == 1
    assert activity['uploads_idle'] is False


@pytest.mark.parametrize('blocked', [
    'unknown',
    'ignored',
    'disabled',
    'paused',
])
def test_retry_rejects_entire_selection_before_side_effects(mcp_client, configured, blocked):
    items = [
        '43',
        'not-in-cache',
    ] if blocked == 'unknown' else ['43']
    if blocked in (
        'ignored',
        'paused',
    ):
        servers.update_server('first', {'ignored_libraries': '1'} if blocked == 'ignored' else {'enabled': False})
    if blocked == 'disabled':
        configured['Themerr']['BOOL_THEMERR_ENABLED'] = False
    result = _call(mcp_client, 'retry_items', {
        'server_id': 'first',
        'item_ids': items,
    }, mcp_client.process_token)
    assert result['isError'] is True
    assert processing.q.qsize() == 0


def test_jellyfin_retry_preserves_the_saved_server_scope(mcp_client):
    data = _data(mcp_client, 'retry_items', {
        'server_id': JELLYFIN,
        'item_ids': ['42'],
    }, mcp_client.process_token)
    assert data['queued_item_ids'] == ['42']
    assert processing.q.queue[0] == (
        JELLYFIN,
        '42',
    )


def test_log_batches_are_redacted_filtered_and_keep_the_cursor(mcp_client, tmp_path, monkeypatch):
    monkeypatch.setattr(log_viewer.Paths, 'LOG_DIR', str(tmp_path))
    (tmp_path / 'themerr.log').write_text(
        '2026-10-09 10:00:00 - WARNING :: Worker : first warning\n'
        f'2026-10-09 10:01:00 - ERROR :: Worker : Authorization: Bearer {mcp_client.read_token}\n',
        encoding='utf-8',
    )
    data = _data(mcp_client, 'get_logs', {
        'source': 'themerr',
        'level': 'ERROR',
        'query': 'authorization',
    })
    assert len(data['entries']) == 1
    assert mcp_client.read_token not in data['entries'][0]['message']
    handler = log_viewer._SessionLogHandler()
    monkeypatch.setattr(logger, '_session_handler', handler)
    try:
        record = logging.LogRecord('themerr', 30, __file__, 1, 'first warning', (), None)
        handler.emit(record)
        data = _data(mcp_client, 'get_logs', {
            'source': 'themerr',
            'cursor': 0,
            'query': 'no match',
        })
        assert data['entries'] == []
        assert data['cursor'] > 0
        handler.emit(record)
        next_page = _data(mcp_client, 'get_logs', {
            'source': 'themerr',
            'cursor': data['cursor'],
        })
        assert len(next_page['entries']) == 1
    finally:
        handler.close()


def test_unexpected_tool_errors_do_not_expose_internal_details(mcp_client, monkeypatch):
    monkeypatch.setattr(mcp_tools.scheduled_tasks, 'job_history', Mock(side_effect=RuntimeError('private secret')))
    result = _call(mcp_client, 'get_activity')
    assert result['isError'] is True
    assert 'Check its logs' in result['content'][0]['text']
    assert 'private secret' not in json.dumps(result)


@pytest.mark.parametrize('header,value', [
    (
        'Host',
        'attacker.example',
    ),
    (
        'Origin',
        'http://attacker.example',
    ),
])
def test_host_and_origin_validation(mcp_client, header, value):
    response = _rpc(mcp_client, 'tools/list', headers={header: value})
    assert response.status_code in (
        403,
        421,
    )


def test_body_limit_is_enforced_without_browser_csrf(mcp_client):
    response = mcp_client.post('/mcp', content=b'x' * (64 * 1024 + 1), headers={
        'Authorization': f'Bearer {mcp_client.read_token}',
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream',
    })
    assert response.status_code == 413


@pytest.mark.parametrize('override', [
    False,
    True,
])
def test_host_configuration_and_lifespans_are_independent(mcp_client, configured, monkeypatch, override):
    configured['Network']['MCP_ALLOWED_HOSTS'] = 'custom.example:20494'
    permitted = 'custom.example:20494'
    if override:
        permitted = 'override.example:20494'
        monkeypatch.setenv('THEMERR_MCP_ALLOWED_HOSTS', permitted)
    # Reuse the application in overlapping and subsequent startups. Each transport
    # reads its own configuration and runs in its own lifespan/event loop.
    for _ in range(2):
        with TestClient(mcp_client.app, base_url=f'http://{permitted}') as restarted:
            restarted.read_token = mcp_client.read_token
            response = _rpc(restarted, 'tools/list', headers={'Origin': f'http://{permitted}'})
            assert response.status_code == 200
            assert len(response.json()['result']['tools']) == 10
            assert _rpc(restarted, 'tools/list', headers={'Host': 'localhost'}).status_code == 421
            if override:
                assert _rpc(restarted, 'tools/list', headers={'Host': 'custom.example:20494'}).status_code == 421
            assert _rpc(mcp_client, 'tools/list').status_code == 200
        assert _rpc(mcp_client, 'tools/list').status_code == 200
