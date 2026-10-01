"""Exercise the public login boundary with real CSRF and signed cookies."""

# standard imports
import json
import logging
import re

# lib imports
import pytest
from werkzeug.security import check_password_hash

# local imports
from common import admin, webapp
from themerr import storage

PASSWORD = 'my unique long test passphrase'


@pytest.fixture
def browser(configured, monkeypatch):
    monkeypatch.setattr(admin, 'HASH_METHOD', 'scrypt:16384:8:1')
    admin._attempts.clear()
    webapp.app.config.update(TESTING=True, WTF_CSRF_ENABLED=True, SESSION_COOKIE_SECURE=False)
    with webapp.app.test_client() as client:
        yield client
    admin._attempts.clear()


def csrf(client, path='/login', **kwargs):
    response = client.get(path, **kwargs)
    return re.search(rb'name="csrf-token" content="([^"]+)"', response.data).group(1).decode()


def create_account(client):
    response = client.get('/setup?token=' + admin.SETUP_TOKEN)
    assert response.status_code == 302
    assert response.headers['Referrer-Policy'] == 'no-referrer'
    token = csrf(client, '/setup')
    return client.post('/setup', data={'csrf_token': token, 'username': 'admin',
                                       'password': PASSWORD, 'confirm_password': PASSWORD})


def sign_in(client, password=PASSWORD, username='admin', query=''):
    token = csrf(client)
    return client.post('/login' + query, data={'csrf_token': token, 'username': username, 'password': password})


def test_setup_requires_console_link_and_csrf_and_creates_only_one_admin(browser):
    assert browser.get('/setup').status_code == 403
    assert browser.get('/setup?token=wrong').status_code == 403
    assert browser.post('/setup', data={'username': 'admin', 'password': PASSWORD}).status_code == 400
    response = create_account(browser)
    assert response.location == '/servers'
    current = admin.account()
    assert current['username'] == 'admin'
    assert PASSWORD not in json.dumps(current)
    assert check_password_hash(current['password_hash'], PASSWORD)
    assert browser.get('/setup?token=' + admin.SETUP_TOKEN).location == '/login'
    assert browser.post('/setup', data={
        'csrf_token': csrf(browser, '/servers'), 'username': 'another', 'password': PASSWORD,
    }).status_code == 302
    assert admin.account() == current
    assert browser.get('/').status_code == 200


@pytest.mark.parametrize('password, confirm, username, message', [
    ('short', 'short', 'admin', b'12 and 256'),
    (PASSWORD, 'different', 'admin', b'do not match'),
    (PASSWORD, PASSWORD, 'a', b'3 and 64'),
])
def test_setup_validation(browser, password, confirm, username, message):
    browser.get('/setup?token=' + admin.SETUP_TOKEN)
    response = browser.post('/setup', data={
        'csrf_token': csrf(browser, '/setup'), 'username': username,
        'password': password, 'confirm_password': confirm,
    })
    assert response.status_code == 200
    assert message in response.data
    assert admin.account() is None


@pytest.mark.parametrize('path', ['/api/settings', '/api/plex/auth', '/api/themes/42',
                                  '/api/servers/server-a/themes/42', '/api/tasks'])
def test_private_apis_require_login(browser, path):
    response = browser.get(path)
    assert response.status_code == 401
    assert response.json == {'message': 'Sign in to continue.'}


def test_pages_require_login_while_health_and_assets_are_public(browser):
    for path in ('/', '/servers', '/settings/', '/activity', '/docs/', '/translations'):
        assert browser.get(path).status_code == 302
    assert browser.get('/status').status_code == 200
    assert browser.get('/favicon.ico').status_code == 200
    assert browser.get('/web/assets/app.css').status_code == 200
    assert b'{% extends' not in browser.get('/web/assets/../templates/home.html').data
    assert b'{% extends' not in browser.get('/web/templates/home.html').data
    assert browser.get('/login').location == '/setup'


def test_login_csrf_session_rotation_logout_and_security_headers(browser):
    create_account(browser)
    token = csrf(browser, '/')
    assert browser.get('/logout').status_code == 405
    assert browser.post('/logout').status_code == 400
    assert browser.post('/logout', data={'csrf_token': token}).location == '/login'
    assert browser.get('/api/settings').status_code == 401
    response = browser.post('/login', data={'username': 'admin', 'password': PASSWORD})
    assert response.status_code == 400
    response = sign_in(browser)
    assert response.location == '/'
    cookie = response.headers['Set-Cookie']
    assert 'HttpOnly' in cookie and 'SameSite=Lax' in cookie
    for path in ('/', '/login', '/servers', '/settings/', '/activity', '/status'):
        response = browser.get(path)
        assert response.headers['X-Frame-Options'] == 'DENY'
        assert "frame-ancestors 'none'" in response.headers['Content-Security-Policy']
        assert "script-src 'self'" in response.headers['Content-Security-Policy']
        assert response.headers['X-Content-Type-Options'] == 'nosniff'
        assert response.headers['Cache-Control'] == 'no-store'
        assert response.headers['Referrer-Policy'] == 'same-origin'
    with browser.session_transaction() as session:
        assert 'setup_authorized' not in session
        assert session['admin_revision'] == admin.account()['revision']
        assert PASSWORD not in str(session)


def test_https_csrf_requires_same_origin_referer(browser):
    admin._save('admin', PASSWORD)
    token = csrf(browser, base_url='https://localhost')
    denied = browser.post('/login', base_url='https://localhost', data={
        'csrf_token': token, 'username': 'admin', 'password': PASSWORD,
    })
    assert denied.status_code == 400
    response = browser.post('/login', base_url='https://localhost', headers={'Referer': 'https://localhost/login'},
                            data={'csrf_token': token, 'username': 'admin', 'password': PASSWORD})
    assert response.status_code == 302


@pytest.mark.parametrize('target', ['https://evil.example', '//evil.example', '/\\evil.example', '//[invalid'])
def test_login_rejects_external_redirects(browser, target):
    admin._save('admin', PASSWORD)
    response = sign_in(browser, query='?next=' + target)
    assert response.location == '/'
    assert browser.get('/login?next=/settings/').location == '/settings/'


def test_generic_login_failures_are_rate_limited_and_counter_expires(browser, monkeypatch):
    admin._save('admin', PASSWORD)
    for index in range(5):
        response = sign_in(browser, password='wrong', username='wrong' if index % 2 else 'admin')
        assert b'The username or password is incorrect.' in response.data
    response = sign_in(browser)
    assert response.status_code == 429
    assert response.headers['Retry-After'] == '900'
    monkeypatch.setattr(admin.time, 'monotonic', lambda: 10**12)
    assert sign_in(browser).status_code == 302


def test_password_change_requires_current_password_and_invalidates_other_sessions(browser):
    create_account(browser)
    second = webapp.app.test_client()
    assert sign_in(second).status_code == 302
    token = csrf(browser, '/settings/')
    response = browser.post('/api/admin/password', data={'csrf_token': token, 'current_password': 'wrong'})
    assert response.status_code == 400
    assert browser.post('/api/admin/password', data={'current_password': PASSWORD}).status_code == 400
    data = {'csrf_token': token, 'current_password': PASSWORD, 'password': 'an even better passphrase',
            'confirm_password': 'mismatch'}
    assert browser.post('/api/admin/password', data=data).status_code == 400
    data['confirm_password'] = data['password']
    assert browser.post('/api/admin/password', data=data).status_code == 200
    assert browser.get('/api/settings').status_code == 200
    assert second.get('/api/settings').status_code == 401
    assert check_password_hash(admin.account()['password_hash'], data['password'])
    admin.reset_password(PASSWORD)
    assert browser.get('/api/settings').status_code == 401


def test_setup_token_is_redacted_from_access_logs():
    record = logging.LogRecord('werkzeug', logging.INFO, '', 0, 'GET %s',
                               ('/setup?token=' + admin.SETUP_TOKEN,), None)
    assert admin._SetupLinkFilter().filter(record)
    assert admin.SETUP_TOKEN not in record.getMessage()
    assert '[redacted]' in record.getMessage()


def test_password_hash_uses_production_scrypt_cost_and_fresh_salts(configured):
    assert admin.HASH_METHOD == 'scrypt:131072:8:1'
    first = admin._save('admin', PASSWORD)
    second = admin._save('admin', PASSWORD)
    assert first['password_hash'].startswith(admin.HASH_METHOD + '$')
    assert first['password_hash'] != second['password_hash']
    assert first['revision'] != second['revision']
    assert PASSWORD not in open(storage.database_path(), 'rb').read().decode(errors='ignore')
