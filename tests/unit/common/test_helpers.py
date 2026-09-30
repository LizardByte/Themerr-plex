"""File, HTTP, health, and formatting helpers without external services."""

# standard imports
import json
from types import SimpleNamespace
from unittest.mock import Mock

# lib imports
import requests

# local imports
from common import helpers


def test_public_ip():
    assert helpers.is_public_ip('8.8.8.8')
    assert not helpers.is_public_ip('192.168.1.2')
    assert not helpers.is_public_ip('bad address')


def test_check_folder_writable(tmp_path, monkeypatch):
    primary = tmp_path / 'primary'
    fallback = tmp_path / 'fallback'
    assert helpers.check_folder_writable(str(fallback), 'data', str(primary)) == (str(primary), True)
    monkeypatch.setattr(helpers.os, 'access', lambda path, mode: str(path) != str(primary))
    assert helpers.check_folder_writable(str(fallback), 'data', str(primary)) == (str(fallback), True)


def test_file_load_save(tmp_path):
    path = tmp_path / 'data.txt'
    assert helpers.file_load(str(path)) is None
    assert helpers.file_save(str(path), 'data')
    assert helpers.file_load(str(path)) == 'data'
    assert not helpers.file_save(str(tmp_path / 'missing' / 'file'), 'data')


def test_docker_healthcheck(monkeypatch):
    calls = []

    def get(url, timeout, verify):
        calls.append((url, timeout, verify))
        if url.startswith('http:'):
            raise requests.ConnectionError()
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr(helpers.requests, 'get', get)
    assert helpers.docker_healthcheck()
    assert calls == [
        ('http://localhost:9494/status', 5, True),
        ('https://localhost:9494/status', 5, False),
    ]
    monkeypatch.setattr(helpers.requests, 'get', lambda **_: SimpleNamespace(status_code=500))
    assert not helpers.docker_healthcheck()


def test_json_get(configured, monkeypatch):
    session = SimpleNamespace(
        get=Mock(return_value=SimpleNamespace(json=lambda: {'id': 1})),
        post=Mock(return_value=SimpleNamespace(json=lambda: {'id': 2})),
    )
    monkeypatch.setattr(helpers.requests, 'Session', lambda: session)
    monkeypatch.setattr(helpers.requests_cache, 'CachedSession', lambda **_: session)
    monkeypatch.setattr(helpers.time, 'sleep', Mock())

    assert helpers.json_get('https://example', cache_time=1, sleep_time=1) == {'id': 1}
    assert helpers.json_get('https://example', request_type='POST') == {'id': 2}
    assert helpers.json_get('https://example', request_type='DELETE') == {}
    helpers.time.sleep.assert_called_once_with(1)


def test_json_get_errors(monkeypatch):
    session = SimpleNamespace(get=Mock(side_effect=requests.ConnectionError()), post=Mock())
    monkeypatch.setattr(helpers.requests, 'Session', lambda: session)
    assert helpers.json_get('https://example') == {}
    session.get.side_effect = None
    session.get.return_value = SimpleNamespace(
        json=lambda: (_ for _ in ()).throw(json.JSONDecodeError('bad', '{', 0)),
    )
    assert helpers.json_get('https://example') == {}


def test_quote_time_and_browser(monkeypatch):
    assert helpers.string_quote('a b') == 'a%20b'
    assert helpers.string_quote('a b', use_plus=True) == 'a+b'
    assert helpers.string_unquote('a%20b') == 'a b'
    assert helpers.string_unquote('a+b', use_plus=True) == 'a b'
    monkeypatch.setattr(helpers.time, 'time', lambda: 0)
    assert helpers.timestamp() == 0
    assert helpers.now() == helpers.timestamp_to_YMDHMS(0)
    assert len(helpers.timestamp_to_YMDHMS(0, separate=True)) == 19
    monkeypatch.setattr(helpers.webbrowser, 'open', lambda **_: True)
    assert helpers.open_url_in_browser('https://example')

    def fail(**_):
        raise helpers.webbrowser.Error('browser missing')

    monkeypatch.setattr(helpers.webbrowser, 'open', fail)
    assert not helpers.open_url_in_browser('https://example')
