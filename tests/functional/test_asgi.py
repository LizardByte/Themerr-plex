"""ASGI migration boundaries: concurrency, signed sessions, bounded bodies, and cleanup."""

# standard imports
import asyncio
import socket
from threading import Event, Thread
import time
from types import SimpleNamespace
from unittest.mock import Mock

# lib imports
from fastapi.testclient import TestClient
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from itsdangerous import TimestampSigner, URLSafeTimedSerializer
import polib
import pytest

# local imports
from common import admin, crypto, mcp_auth, webapp
from common import http as browser_http
from common.definitions import Paths
from jellyfin import repository
from plex import plexapi
from tests.http_helpers import get_session, set_session
from tests.unit.common.test_locales import write_catalog


@pytest.fixture
def browser(configured, monkeypatch):
    monkeypatch.setattr(admin, 'HASH_METHOD', 'scrypt:16384:8:1')
    current = admin._save('admin', 'a unique test password')
    with TestClient(webapp.create_app(https_only=False), base_url='http://localhost',
                    follow_redirects=False) as client:
        set_session(client, {'admin_revision': current['revision']})
        yield client


def test_signed_cookie_tampering_cannot_access_private_routes(browser):
    cookie = browser.cookies.get('session')
    data, signature = cookie.rsplit('.', 1)
    altered = data + '.' + ('A' if signature[0] != 'A' else 'B') + signature[1:]
    browser.cookies.clear()
    browser.cookies.set('session', altered, domain='localhost.local', path='/')
    assert browser.get('/api/settings').status_code == 401
    assert browser.get('/').status_code == 302


def test_head_requests_preserve_get_headers_without_saving_settings(browser, monkeypatch):
    save = Mock()
    monkeypatch.setattr(webapp.config, 'save_config', save)
    for path in ('/', '/servers', '/settings/', '/api/settings', '/status'):
        get = browser.get(path)
        head = browser.head(path)
        assert head.status_code == get.status_code == 200
        assert head.content == b''
        assert head.headers['content-type'] == get.headers['content-type']
        assert head.headers['content-length'] == get.headers['content-length']
    save.assert_not_called()


@pytest.mark.parametrize('invalid', ['signature', 'session', 'expired'])
def test_csrf_tokens_are_signed_bound_to_session_and_expire(browser, monkeypatch, invalid):
    browser.get('/settings/')
    value = get_session(browser)['csrf_token']
    serializer = URLSafeTimedSerializer(browser.app.state.secret_key, salt='csrf-token')
    if invalid == 'signature':
        token = 'not-a-signed-token'
    elif invalid == 'session':
        token = serializer.dumps('another-browser-session')
    else:
        with monkeypatch.context() as patch:
            patch.setattr(TimestampSigner, 'get_timestamp', lambda self: int(time.time()) - 3601)
            token = serializer.dumps(value)
    response = browser.post('/logout', headers={'X-CSRFToken': token})
    assert response.status_code == 400
    assert browser.get('/api/settings').status_code == 200


@pytest.mark.parametrize('referer', [
    'https://localhost:9495/settings/', 'http://localhost:9494/settings/',
    'https://evil.example:9494/settings/', 'https://localhost:invalid/settings/',
])
def test_https_csrf_checks_scheme_host_and_port(browser, referer):
    browser.get('https://localhost:9494/settings/')
    token = URLSafeTimedSerializer(browser.app.state.secret_key, salt='csrf-token').dumps(
        get_session(browser)['csrf_token'],
    )
    response = browser.post('https://localhost:9494/logout',
                            headers={'Referer': referer, 'X-CSRFToken': token})
    assert response.status_code == 400
    assert browser.post('https://localhost:9494/logout', headers={
        'Referer': 'https://localhost:9494/settings/', 'X-CSRFToken': token,
    }).status_code == 302


def test_chunked_requests_cannot_bypass_the_body_limit(browser):
    async def oversized_body():
        yield b'x' * (64 * 1024)
        yield b'x'

    async def submit():
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=browser.app),
                                      base_url='http://localhost', cookies=browser.cookies) as client:
            response = await client.post('/api/directories', content=oversized_body())
            assert response.status_code == 413
            assert response.json() == {'message': 'Request body is too large.'}
            assert response.headers['Cache-Control'] == 'no-store'

    asyncio.run(submit())


@pytest.mark.parametrize('multipart', [False, True])
def test_oversized_forms_are_rejected_before_parsing(browser, multipart):
    field = 'x' * (64 * 1024)
    payload = {'files': {'General|LOCALE': (None, field)}} if multipart else {'data': {'General|LOCALE': field}}
    response = browser.post('/api/settings', **payload)
    assert response.status_code == 413
    assert response.json() == {'message': 'Request body is too large.'}


@pytest.mark.parametrize('payload, message', [
    ({'data': {f'field-{index}': 'value' for index in range(257)}}, 'Too many fields.'),
    ({'files': [(f'field-{index}', (None, 'value')) for index in range(257)]}, 'Too many fields.'),
    ({'files': {'upload': ('theme.mp3', b'audio', 'audio/mpeg')}}, 'Too many files.'),
])
def test_browser_forms_reject_excess_fields_and_uploads(browser, payload, message):
    browser.get('/settings/')
    token = URLSafeTimedSerializer(browser.app.state.secret_key, salt='csrf-token').dumps(
        get_session(browser)['csrf_token'],
    )
    response = browser.post('/api/settings', headers={'X-CSRFToken': token}, **payload)
    assert response.status_code == 400
    assert response.json()['message'].startswith(message)


def test_blocking_plex_requests_do_not_block_the_event_loop(browser, monkeypatch):
    started, release = Event(), Event()

    def fetch_item(rating_key):
        started.set()
        assert release.wait(timeout=5)
        return SimpleNamespace(theme=None)

    server = Mock()
    server.fetchItem.side_effect = fetch_item
    monkeypatch.setattr(plexapi, 'setup_plexapi', lambda: server)

    async def concurrent_requests():
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=browser.app),
                                      base_url='http://localhost', cookies=browser.cookies) as client:
            playback = asyncio.create_task(client.get('/api/themes/42'))
            try:
                assert await asyncio.to_thread(started.wait, 2)
                response = await asyncio.wait_for(client.get('/status'), timeout=2)
                assert response.status_code == 200
                assert not playback.done()
            finally:
                release.set()
                assert (await playback).status_code == 404

    asyncio.run(concurrent_requests())


@pytest.mark.parametrize('stage', ['headers', 'body'])
def test_asgi_send_failure_closes_the_audio_connection(stage):
    upstream = Mock(status_code=200)
    upstream.iter_content.return_value = iter([b'audio'])

    async def disconnected():
        scope = {'type': 'http', 'method': 'GET', 'asgi': {'spec_version': '2.4'}}

        async def receive():
            return {'type': 'http.disconnect'}

        async def send(message):
            if message['type'] == ('http.response.start' if stage == 'headers' else 'http.response.body'):
                raise OSError('browser disconnected')

        response = webapp.ThemeAudioResponse(upstream, 42, {'Content-Type': 'audio/mpeg'})
        await response(scope, receive, send)

    asyncio.run(disconnected())
    upstream.close.assert_called_once()


def test_disconnect_during_blocked_audio_read_releases_the_upstream():
    started, release = Event(), Event()

    def slow_audio(**kwargs):
        started.set()
        assert release.wait(timeout=5)
        yield b'audio'

    upstream = Mock(status_code=200)
    upstream.iter_content.side_effect = slow_audio
    upstream.close.side_effect = release.set

    async def disconnect():
        scope = {'type': 'http', 'method': 'GET', 'asgi': {'spec_version': '2.3'}}

        async def receive():
            assert await asyncio.to_thread(started.wait, 2)
            return {'type': 'http.disconnect'}

        async def send(message):
            pass

        response = webapp.ThemeAudioResponse(upstream, 42, {'Content-Type': 'audio/mpeg'})
        try:
            await asyncio.wait_for(response(scope, receive, send), timeout=3)
        finally:
            release.set()

    asyncio.run(disconnect())
    upstream.close.assert_called_once()


def test_template_translation_follows_locale_changes(browser, monkeypatch, tmp_path):
    monkeypatch.setattr(Paths, 'LOCALE_DIR', str(tmp_path))
    catalog_dir = tmp_path / 'fr' / 'LC_MESSAGES'
    catalog_dir.mkdir(parents=True)
    catalog = polib.POFile()
    catalog.metadata = {'Content-Type': 'text/plain; charset=UTF-8'}
    catalog.append(polib.POEntry(msgid='Settings', msgstr='Paramètres'))
    catalog.save_as_mofile(str(catalog_dir / (browser_http.locales.default_domain + '.mo')))
    monkeypatch.setattr(browser_http.locales, 'get_locale', lambda: 'fr')
    assert 'Paramètres' in browser.get('/settings/').text
    monkeypatch.setattr(browser_http.locales, 'get_locale', lambda: 'en')
    assert 'Paramètres' not in browser.get('/settings/').text


def test_saved_locale_changes_templates_schema_labels_and_survives_restart(browser, monkeypatch, tmp_path):
    monkeypatch.setattr(Paths, 'LOCALE_DIR', str(tmp_path / 'catalogs'))
    root = tmp_path / 'catalogs'
    write_catalog(root / 'themerr.po', Settings='', Locale='')
    path = root / 'fr' / 'LC_MESSAGES' / 'themerr.po'
    write_catalog(path, Settings='Ancien').save_as_mofile(str(path.with_suffix('.mo')))
    write_catalog(path, Settings='Paramètres', Locale='Langue')
    browser.get('/settings/')
    token = URLSafeTimedSerializer(browser.app.state.secret_key, salt='csrf-token').dumps(
        get_session(browser)['csrf_token'],
    )
    assert browser.post('/api/settings', data={'General|LOCALE': 'fr'},
                        headers={'X-CSRFToken': token}).status_code == 200
    response = browser.get('/settings/')
    assert '<html lang="fr"' in response.text
    assert '<title>Paramètres' in response.text
    assert '>Langue</label>' in response.text
    assert browser.get('/translations').json()['Settings'] == 'Paramètres'
    saved = webapp.config.CONFIG
    webapp.config.create_config(saved.filename)
    with TestClient(webapp.create_app(https_only=False), base_url='http://localhost') as restarted:
        set_session(restarted, {'admin_revision': admin.account()['revision']})
        assert '<title>Paramètres' in restarted.get('/settings/').text
    assert browser.post('/api/settings', data={'General|LOCALE': 'en'},
                        headers={'X-CSRFToken': token}).status_code == 200
    assert '<html lang="en"' in browser.get('/settings/').text
    assert '<title>Settings' in browser.get('/settings/').text
    assert not (root / 'en').exists()


def test_api_documentation_requires_session_and_uses_local_assets(browser):
    page = browser.get('/api/docs')
    assert page.status_code == 200
    assert 'id="swagger-ui"' in page.text
    assert '/web/assets/api_docs.js' in page.text
    assert '/web/assets/api_docs.css' in page.text
    assert '<script type="module"' in page.text
    assert '<script defer' not in page.text
    assert 'cdn.jsdelivr.net' not in page.text
    assert 'script-src \'self\'' in page.headers['Content-Security-Policy']
    assert 'href="/api/docs"' in browser.get('/settings/').text
    browser.cookies.clear()
    assert browser.get('/api/docs').status_code == 401
    assert browser.get('/api/openapi.json').status_code == 401


def test_theme_switcher_is_shared_by_workspace_swagger_and_sign_in(browser):
    for path in ('/settings/', '/api/docs'):
        page = browser.get(path)
        assert page.status_code == 200
        assert 'data-color-theme' in page.text
        assert all(f'data-theme-icon="{mode}"' in page.text for mode in ('light', 'dark', 'auto'))
        assert all(f'data-lucide="{icon}"' in page.text for icon in ('sun', 'moon', 'sun-moon'))
        script = page.text.index('<script src="/web/assets/color_theme.js')
        assert script < page.text.index('rel="stylesheet"')
        assert "script-src 'self';" in page.headers['Content-Security-Policy']
    assert browser.get('/web/assets/color_theme.js').status_code == 200
    browser.cookies.clear()
    login = browser.get('/login')
    assert login.status_code == 200
    assert 'data-color-theme' in login.text
    assert '/web/assets/color_theme.js' in login.text


def test_openapi_describes_request_bodies_authentication_and_unique_operations(browser):
    response = browser.get('/api/openapi.json')
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    schema = response.json()
    paths = schema['paths']
    assert '/api/docs' not in paths
    assert '/' not in paths
    assert schema['components']['securitySchemes']['BrowserSession']['in'] == 'cookie'
    ids = []
    for path, methods in paths.items():
        assert 'head' not in methods
        for method, operation in methods.items():
            ids.append(operation['operationId'])
            if path != '/status':
                assert operation['security'] == [{'BrowserSession': []}]
            if method == 'post':
                assert any(p['name'] == 'X-CSRFToken' for p in operation['parameters'])
    assert len(ids) == len(set(ids))
    settings = paths['/api/settings']['post']['requestBody']['content']['application/x-www-form-urlencoded']
    assert settings['example'] == {'General|LOCALE': 'en'}
    assert 'requestBody' not in paths['/api/servers/{server_id}']['delete']
    body = paths['/api/servers/discover']['post']['requestBody']['content']['application/json']
    assert body['schema']['properties']['source']['enum'] == ['account', 'local']
    assert '201' in paths['/api/servers']['post']['responses']
    assert '200' not in paths['/api/servers']['post']['responses']
    assert '202' in paths['/api/tasks/refresh']['post']['responses']
    assert '200' not in paths['/api/tasks/refresh']['post']['responses']
    audio = paths['/api/themes/{rating_key}']['get']
    assert any(parameter['name'] == 'Range' for parameter in audio['parameters'])
    for status in ('200', '206'):
        assert audio['responses'][status]['content']['audio/mpeg']['schema']['format'] == 'binary'
    assert '416' in audio['responses']
    poster = paths['/api/themes/{rating_key}/poster']['get']
    assert poster['responses']['200']['content']['image/jpeg']['schema']['format'] == 'binary'
    assert '404' in poster['responses']
    assert '502' in poster['responses']
    assert 'security' not in paths['/status']['get']


def test_documentation_supplies_session_bound_csrf_defaults(browser):
    browser.get('/api/docs')
    schema = browser.get('/api/openapi.json').json()
    parameters = schema['paths']['/api/settings']['post']['parameters']
    token = next(p['schema']['default'] for p in parameters if p['name'] == 'X-CSRFToken')
    response = browser.post('/api/settings', data={'General|LOCALE': 'en'}, headers={'X-CSRFToken': token})
    assert response.status_code == 200
    # Session tokens never enter the installation-wide cached schema.
    parameters = browser.app.openapi()['paths']['/api/settings']['post']['parameters']
    assert all('default' not in p['schema'] for p in parameters if p['name'] == 'X-CSRFToken')


def test_unexpected_api_failure_keeps_generic_errors_and_security_headers(browser, monkeypatch):
    from themerr import deployment_status
    monkeypatch.setattr(deployment_status, 'publication_status', Mock(side_effect=RuntimeError('private details')))
    with TestClient(browser.app, base_url='http://localhost', raise_server_exceptions=False,
                    cookies=browser.cookies) as client:
        response = client.get('/api/themerrdb')
    assert response.status_code == 500
    assert response.json() == {'message': 'Internal Server Error'}
    assert response.headers['X-Frame-Options'] == 'DENY'
    assert response.headers['Cache-Control'] == 'no-store'


@pytest.mark.parametrize('tls,mcp_http', [
    pytest.param(False, True),
    pytest.param(True, False),
    pytest.param(True, True),
])
def test_uvicorn_serves_http_and_https_and_releases_its_socket(configured, monkeypatch, tmp_path, tls, mcp_http):
    configured['Network'].update({
        'HTTP_HOST': '127.0.0.1',
        'HTTP_PORT': 0,
        'SSL': tls,
        'MCP_HTTP': mcp_http,
    })
    with socket.socket() as port_probe:
        port_probe.bind((
            '127.0.0.1',
            0,
        ))
        configured['Jellyfin']['REPOSITORY_HTTP_PORT'] = port_probe.getsockname()[1]
    monkeypatch.setattr(crypto, 'CERT_FILE', str(tmp_path / 'cert.pem'))
    monkeypatch.setattr(crypto, 'KEY_FILE', str(tmp_path / 'key.pem'))
    failures = []

    def run_server():
        try:
            webapp.start_webapp()
        except BaseException as error:
            failures.append(error)

    thread = Thread(target=run_server, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            server = webapp._server
            if server is not None and server.started:
                break
            assert not failures
            time.sleep(0.02)
        else:
            pytest.fail('Uvicorn did not start')
        port = server.servers[0].sockets[0].getsockname()[1]
        url = f'{"https" if tls else "http"}://127.0.0.1:{port}'
        with httpx2.Client(verify=False, trust_env=False) as client:
            assert client.get(url + '/status').json() == {'result': 'success', 'message': 'Ok'}
            assert client.get(url + '/api/settings').status_code == 401
            response = client.get(url + '/setup?token=' + admin.SETUP_TOKEN)
            assert response.status_code == 302
            assert ('secure' in response.headers['set-cookie'].lower()) is tls
            assert client.get(url + '/setup').status_code == 200
        assert server.config.proxy_headers is False
        assert server.config.lifespan == 'on'
        monkeypatch.setattr(admin, 'HASH_METHOD', 'scrypt:16384:8:1')
        admin._save('admin', 'a unique MCP test password')
        token = mcp_auth.create_token('read')

        async def query_mcp(target_url):
            async with httpx2.AsyncClient(verify=target_url.startswith('http:'), trust_env=False,
                                          headers={'Authorization': f'Bearer {token}'}) as http_client:
                transport = streamable_http_client(f'{target_url}/mcp', http_client=http_client)
                async with Client(transport) as mcp_client:
                    tools = await mcp_client.list_tools()
                    assert any(tool.name == 'inspect_theme' for tool in tools.tools)
                    result = await mcp_client.call_tool('get_activity')
                    assert result.is_error is False
                    assert 'queued_items' in result.structured_content
                    denied = await mcp_client.call_tool('refresh_libraries')
                    assert denied.is_error is True

        asyncio.run(asyncio.wait_for(query_mcp(url), timeout=10))
        if tls:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and repository.http_port() is None:
                time.sleep(0.02)
            assert repository.http_port() == configured['Jellyfin']['REPOSITORY_HTTP_PORT']
            companion = repository._server
            http_url = f'http://127.0.0.1:{repository.http_port()}'
            with httpx2.Client(trust_env=False) as client:
                assert client.get(f'{http_url}/settings/').status_code == 404
                assert client.post(f'{http_url}/api/mcp/tokens', json={}).status_code == 404
                assert client.post(f'{http_url}/mcp', json={}).status_code == (401 if mcp_http else 404)
            if mcp_http:
                assert repository.mcp_http_port() == repository.http_port()
                asyncio.run(asyncio.wait_for(query_mcp(http_url), timeout=10))
            else:
                assert repository.mcp_http_port() is None
        else:
            assert repository.http_port() is None
    finally:
        webapp.stop_webapp()
        thread.join(timeout=10)
    assert not thread.is_alive()
    assert not failures
    assert webapp._server is None
    assert all(not listener.sockets for listener in server.servers)
    assert repository.http_port() is None
    if tls:
        assert all(not listener.sockets for listener in companion.servers)


def test_server_failure_releases_shutdown_waiters(configured, monkeypatch):
    configured['Network']['SSL'] = False
    server = Mock()
    server.run.side_effect = RuntimeError('bind failed')
    monkeypatch.setattr(webapp.uvicorn, 'Server', lambda config: server)
    with pytest.raises(RuntimeError, match='bind failed'):
        webapp.start_webapp()
    assert webapp._server is None
    assert webapp._server_stopped.is_set()
    webapp.stop_webapp()
