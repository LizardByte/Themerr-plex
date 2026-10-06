"""Cookie settings are encrypted, migrated, and redacted without plaintext fallback."""

# standard imports
import json
from pathlib import Path
from unittest.mock import Mock

# lib imports
from configobj import ConfigObj
from cryptography.fernet import Fernet
import pytest

# local imports
from common import config, credentials


def cookie_export(value='private-session'):
    """Return a browser cookie export with a recognizable private value."""
    return json.dumps([{
        'domain': '.youtube.com',
        'path': '/',
        'secure': True,
        'name': 'SESSION',
        'value': value,
    }])


@pytest.mark.parametrize('external_key', (
    False,
    True,
))
def test_cookie_storage_encrypts_large_exports_and_survives_reload(configured, tmp_path, monkeypatch, external_key):
    if external_key:
        key_file = tmp_path / 'external.key'
        key_file.write_bytes(Fernet.generate_key())
        monkeypatch.setenv(credentials.KEY_FILE_ENV, str(key_file))
        monkeypatch.setenv('THEMERR_DOCKER', 'true')
    vault_write = Mock(wraps=credentials.keyring.set_password)
    monkeypatch.setattr(credentials.keyring, 'set_password', vault_write)
    raw = cookie_export('private-session' * 1000)
    configured['Themerr']['STR_YOUTUBE_COOKIES'] = raw
    assert config.save_config(config=configured)
    encrypted = configured['Themerr']['STR_YOUTUBE_COOKIES']
    assert encrypted.startswith(credentials.SETTING_PREFIX)
    assert 'private-session' not in Path(configured.filename).read_text(encoding='utf-8')
    assert config.youtube_cookies() == raw
    assert config.decode_config(configured)['Themerr']['STR_YOUTUBE_COOKIES'] == ''
    if external_key:
        vault_write.assert_not_called()
    else:
        assert len(vault_write.call_args.args[2]) == 44
    reloaded = config.create_config(configured.filename)
    assert reloaded['Themerr']['STR_YOUTUBE_COOKIES'] == encrypted
    assert config.youtube_cookies() == raw


def test_plaintext_cookies_are_migrated_without_losing_settings(configured):
    legacy = ConfigObj({
        'Themerr': {'STR_YOUTUBE_COOKIES': cookie_export()},
        'General': {'LAUNCH_BROWSER': False},
    }, encoding='UTF-8')
    legacy.filename = configured.filename
    legacy.write()
    reloaded = config.create_config(configured.filename)
    assert reloaded['General']['LAUNCH_BROWSER'] is False
    assert config.youtube_cookies() == cookie_export()
    assert 'private-session' not in Path(reloaded.filename).read_text(encoding='utf-8')


def test_failed_migration_preserves_the_original_file(configured, monkeypatch):
    legacy = ConfigObj({'Themerr': {'STR_YOUTUBE_COOKIES': cookie_export()}}, encoding='UTF-8')
    legacy.filename = configured.filename
    legacy.write()
    original = Path(legacy.filename).read_bytes()
    monkeypatch.setattr(credentials.keyring, 'get_password', Mock(side_effect=RuntimeError('vault unavailable')))
    with pytest.raises(OSError, match='securely save'):
        config.create_config(legacy.filename)
    assert Path(legacy.filename).read_bytes() == original


@pytest.mark.parametrize('failure', (
    'vault',
    'missing-file',
    'invalid-file',
    'docker',
))
def test_unavailable_secure_storage_never_writes_plaintext(configured, tmp_path, monkeypatch, failure):
    original = Path(configured.filename).read_bytes()
    if failure == 'vault':
        monkeypatch.setattr(credentials.keyring, 'set_password', Mock(side_effect=RuntimeError('vault unavailable')))
    elif failure in ('missing-file', 'invalid-file'):
        key_file = tmp_path / 'external.key'
        if failure == 'invalid-file':
            key_file.write_bytes(b'invalid')
        monkeypatch.setenv(credentials.KEY_FILE_ENV, str(key_file))
    else:
        monkeypatch.setenv('THEMERR_DOCKER', 'true')
    configured['Themerr']['STR_YOUTUBE_COOKIES'] = cookie_export()
    assert not config.save_config(config=configured)
    assert Path(configured.filename).read_bytes() == original


def test_missing_key_and_tampered_ciphertext_are_rejected(configured, monkeypatch):
    plaintext = cookie_export()
    encrypted = credentials.encrypt_setting(plaintext)
    with pytest.raises(credentials.TokenStorageError, match='decrypt'):
        credentials.decrypt_setting(encrypted[:-10] + 'tampered')
    monkeypatch.setattr(credentials.keyring, 'get_password', lambda *_: None)
    with pytest.raises(credentials.TokenStorageError, match='key is unavailable'):
        credentials.decrypt_setting(encrypted)
    with pytest.raises(credentials.TokenStorageError, match='not encrypted'):
        credentials.decrypt_setting(plaintext)
