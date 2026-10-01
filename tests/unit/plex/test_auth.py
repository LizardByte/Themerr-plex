"""Plex browser sign-in and credential persistence without network access."""

# standard imports
from urllib.parse import parse_qs
from unittest.mock import Mock

# lib imports
from cryptography.fernet import Fernet
from keyring.errors import NoKeyringError
import pytest
import requests

# local imports
from common import config
from plex import auth, token_store
from themerr import storage


def test_credentials_persist_without_exposing_legacy_token(configured, tmp_path):
    """Only a token obtained through sign-in is read by the Plex client."""
    assert 'PLEX_TOKEN' not in configured['Plex']
    assert auth.get_token() == ''
    identifier = auth._client_identifier()
    assert identifier == auth._client_identifier()
    assert len(identifier) == 32

    auth.set_token('plex-issued-token')
    assert storage.get_credentials() == {'client_id': identifier}
    assert (tmp_path / 'themerr-plex.db').is_file()
    assert b'plex-issued-token' not in (tmp_path / 'themerr-plex.db').read_bytes()
    assert not (tmp_path / 'plex-auth.json').exists()
    assert auth.get_token() == 'plex-issued-token'
    auth.disconnect()
    assert auth.get_token() == ''
    assert storage.get_credentials() == {'client_id': identifier}


def test_headless_token_uses_external_key(configured, tmp_path, monkeypatch):
    key_path = tmp_path / 'plex.key'
    key_path.write_bytes(Fernet.generate_key())
    monkeypatch.setenv('THEMERR_DOCKER', 'True')
    monkeypatch.setenv(token_store.KEY_FILE_ENV, str(key_path))

    auth.set_token('plex-issued-token')
    encrypted = storage.get_encrypted_token()
    assert encrypted and 'plex-issued-token' not in encrypted
    assert b'plex-issued-token' not in (tmp_path / 'themerr-plex.db').read_bytes()
    storage.close()
    assert auth.get_token() == 'plex-issued-token'

    key_path.write_bytes(Fernet.generate_key())
    assert auth.get_token() == ''
    auth.disconnect()
    assert storage.get_encrypted_token() == ''


def test_headless_requires_external_key(configured, monkeypatch):
    monkeypatch.setenv('THEMERR_DOCKER', 'True')
    with pytest.raises(token_store.TokenStorageError, match='mounted secret'):
        auth.set_token('plex-issued-token')
    assert storage.get_encrypted_token() == ''


@pytest.mark.parametrize('error', [
    NoKeyringError('No credential store'), OSError('Native vault failure'), RuntimeError('Native vault failure'),
])
def test_unavailable_os_credential_store_does_not_save_plaintext(configured, tmp_path, monkeypatch, error):
    monkeypatch.setattr(token_store.keyring, 'set_password',
                        Mock(side_effect=error))

    with pytest.raises(token_store.TokenStorageError, match='credential store'):
        auth.set_token('plex-issued-token')
    assert auth.get_token() == ''
    assert b'plex-issued-token' not in (tmp_path / 'themerr-plex.db').read_bytes()


@pytest.mark.parametrize('operation', ['get_password', 'delete_password'])
def test_native_credential_errors_are_reported_as_store_failures(configured, monkeypatch, operation):
    error = RuntimeError('Native vault failure')
    monkeypatch.setattr(token_store.keyring, operation, Mock(side_effect=error))
    handler = token_store.get_token if operation == 'get_password' else token_store.delete_token
    with pytest.raises(token_store.TokenStorageError, match='credential store') as raised:
        handler(auth._client_identifier())
    assert raised.value.__cause__ is error


def test_old_config_token_is_dropped(tmp_path, monkeypatch):
    """Upgrading must not silently keep using a manually supplied token."""
    path = tmp_path / 'config.ini'
    path.write_text('[Plex]\nPLEX_TOKEN = old-manual-token\n', encoding='utf-8')
    with monkeypatch.context() as patch:
        patch.setattr(config, 'CONFIG', config.CONFIG)
        settings = config.create_config(str(path))
    assert 'PLEX_TOKEN' not in settings['Plex']
    assert 'PLEX_TOKEN' not in path.read_text(encoding='utf-8')


def test_start_login_uses_stable_client_and_plex_auth_url(configured, monkeypatch):
    response = Mock()
    response.json.return_value = {'id': 123, 'code': 'strong-code'}
    post = Mock(return_value=response)
    monkeypatch.setattr(auth.requests, 'post', post)

    login = auth.start_login()
    assert login['pin_id'] == 123
    assert login['code'] == 'strong-code'
    assert login['auth_url'].startswith('https://app.plex.tv/auth#?')
    assert parse_qs(login['auth_url'].split('#?', 1)[1]) == {
        'clientID': [auth._client_identifier()],
        'code': ['strong-code'],
        'context[device][product]': ['Themerr-plex'],
    }
    assert post.call_args.kwargs['data'] == {'strong': 'true'}
    assert post.call_args.kwargs['headers']['X-Plex-Client-Identifier'] == auth._client_identifier()
    assert post.call_args.kwargs['timeout'] == auth.TIMEOUT


@pytest.mark.parametrize('pin', [{'code': 'missing-id'}, {'id': 1, 'code': ''}, {'id': 'bad', 'code': 'x'}])
def test_start_login_rejects_bad_pin(configured, monkeypatch, pin):
    response = Mock()
    response.json.return_value = pin
    monkeypatch.setattr(auth.requests, 'post', Mock(return_value=response))
    with pytest.raises((KeyError, ValueError)):
        auth.start_login()


def test_check_login_pending_then_issued(configured, monkeypatch):
    response = Mock()
    response.json.side_effect = [{'authToken': None}, {'authToken': 'issued'}]
    get = Mock(return_value=response)
    monkeypatch.setattr(auth.requests, 'get', get)
    assert auth.check_login(123, 'strong-code') == ''
    assert auth.check_login(123, 'strong-code') == 'issued'
    assert get.call_args.args == ('https://plex.tv/api/v2/pins/123',)
    assert get.call_args.kwargs['params'] == {'code': 'strong-code'}
    assert get.call_args.kwargs['timeout'] == auth.TIMEOUT


def test_start_login_propagates_http_error(configured, monkeypatch):
    response = Mock()
    response.raise_for_status.side_effect = requests.HTTPError('Plex unavailable')
    monkeypatch.setattr(auth.requests, 'post', Mock(return_value=response))
    with pytest.raises(requests.HTTPError):
        auth.start_login()
