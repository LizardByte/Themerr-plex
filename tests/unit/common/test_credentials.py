"""Generic encryption configuration retains old tokens and separate server namespaces."""

# lib imports
from cryptography.fernet import Fernet
from keyring.errors import PasswordDeleteError
import pytest

# local imports
from common import credentials
from common.definitions import Names


@pytest.mark.parametrize('client_id', (
    'account',
    'jellyfin:server',
))
def test_repository_rename_keeps_legacy_credentials(configured, client_id):
    credentials.keyring.set_password(Names.legacy_name, client_id, 'old-secret')
    assert credentials.get_token(client_id) == 'old-secret'
    credentials.save_token(client_id, 'new-secret')
    assert credentials.get_token(client_id) == 'new-secret'
    credentials.delete_token(client_id)
    assert credentials.get_token(client_id) == ''
    assert credentials.keyring.get_password(Names.legacy_name, client_id) is None
    assert credentials.keyring.get_password(credentials.SERVICE, client_id) is None


def test_legacy_credential_is_removed_when_new_service_is_empty(configured, monkeypatch):
    backend_delete = credentials.keyring.delete_password

    def delete(service, client):
        if credentials.keyring.get_password(service, client) is None:
            raise PasswordDeleteError('Missing credential')
        backend_delete(service, client)

    monkeypatch.setattr(credentials.keyring, 'delete_password', delete)
    credentials.keyring.set_password(Names.legacy_name, 'account', 'old-secret')
    credentials.delete_token('account')
    assert credentials.get_token('account') == ''


def test_legacy_key_alias_can_be_renamed_without_losing_tokens(configured, tmp_path, monkeypatch):
    key = tmp_path / 'tokens.key'
    key.write_bytes(Fernet.generate_key())
    monkeypatch.setenv(credentials.LEGACY_KEY_FILE_ENV, str(key))
    credentials.save_token('account', 'plex-account')
    credentials.save_token('jellyfin:server-one', 'jellyfin-key')
    monkeypatch.delenv(credentials.LEGACY_KEY_FILE_ENV)
    monkeypatch.setenv(credentials.KEY_FILE_ENV, str(key))
    assert credentials.get_token('account') == 'plex-account'
    assert credentials.get_token('jellyfin:server-one') == 'jellyfin-key'
    assert credentials.get_token('jellyfin:server-two') == ''
    credentials.delete_token('jellyfin:server-one')
    assert credentials.get_token('jellyfin:server-one') == ''
    assert credentials.get_token('account') == 'plex-account'


def test_generic_key_takes_precedence_over_legacy_alias(configured, tmp_path, monkeypatch):
    key = tmp_path / 'tokens.key'
    key.write_bytes(Fernet.generate_key())
    monkeypatch.setenv(credentials.LEGACY_KEY_FILE_ENV, str(tmp_path / 'missing.key'))
    monkeypatch.setenv(credentials.KEY_FILE_ENV, str(key))
    credentials.save_token('jellyfin:server', 'key')
    assert credentials.get_token('jellyfin:server') == 'key'
