"""Generic encryption configuration retains old tokens and separate server namespaces."""

from cryptography.fernet import Fernet

from common import credentials


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
