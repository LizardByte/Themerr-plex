"""Store credentials outside plaintext application data."""

# standard imports
import os
from pathlib import Path
from threading import RLock

# lib imports
from cryptography.fernet import Fernet, InvalidToken
import keyring
from keyring.errors import PasswordDeleteError

# local imports
from common.definitions import Names
from themerr import storage


SERVICE = Names.name
KEY_FILE_ENV = 'THEMERR_TOKEN_KEY_FILE'
LEGACY_KEY_FILE_ENV = 'THEMERR_PLEX_TOKEN_KEY_FILE'
STORE_UNAVAILABLE = 'The OS credential store is unavailable.'
SETTING_PREFIX = 'fernet:v1:'
_SETTINGS_KEY = 'configuration-encryption-key'
_settings_lock = RLock()


class TokenStorageError(OSError):
    """The configured secure token store cannot be used."""


def _cipher() -> Fernet | None:
    """Return encryption from an external key file, or use the desktop vault.

    Returns
    -------
    Fernet or None
        Cipher for an external key, or ``None`` for the OS credential store.

    Raises
    ------
    TokenStorageError
        The key is missing or invalid in a headless installation.
    """
    key_path = os.environ.get(KEY_FILE_ENV) or os.environ.get(LEGACY_KEY_FILE_ENV)
    if key_path:
        try:
            return Fernet(Path(key_path).read_bytes().strip())
        except (
            OSError,
            ValueError,
        ) as exc:
            raise TokenStorageError(f'Unable to read a valid token encryption key from {KEY_FILE_ENV}.') from exc
    if os.environ.get('THEMERR_DOCKER'):
        raise TokenStorageError(f'Set {KEY_FILE_ENV} to a mounted secret before connecting a media server.')
    return None


def get_token(client_id: str) -> str:
    """Read a token from the selected secure store.

    Parameters
    ----------
    client_id : str
        Installation-scoped credential identifier.

    Returns
    -------
    str
        Stored token, or an empty string when not signed in.
    """
    cipher = _cipher()
    if cipher is not None:
        encrypted = storage.get_encrypted_token(_namespace(client_id))
        if not encrypted:
            return ''
        try:
            return cipher.decrypt(encrypted.encode('ascii')).decode('utf-8')
        except (
            InvalidToken,
            UnicodeError,
        ) as exc:
            raise TokenStorageError('The encryption key does not match the stored token.') from exc
    try:
        return (
            keyring.get_password(SERVICE, client_id)
            or keyring.get_password(Names.legacy_name, client_id)
            or ''
        )
    # Native backends can raise errors outside keyring's exception hierarchy.
    except Exception as exc:
        raise TokenStorageError(STORE_UNAVAILABLE) from exc


def save_token(client_id: str, token: str) -> None:
    """Persist a server token without storing plaintext in SQLite.

    Parameters
    ----------
    client_id : str
        Installation-scoped credential identifier.
    token : str
        Media-server account token or API key.
    """
    cipher = _cipher()
    if cipher is not None:
        storage.save_encrypted_token(cipher.encrypt(token.encode('utf-8')).decode('ascii'), _namespace(client_id))
        return
    try:
        keyring.set_password(SERVICE, client_id, token)
    except Exception as exc:
        raise TokenStorageError(STORE_UNAVAILABLE) from exc


def delete_token(client_id: str) -> None:
    """Remove this installation's saved server token.

    Parameters
    ----------
    client_id : str
        Installation-scoped credential identifier.
    """
    storage.save_encrypted_token(None, _namespace(client_id))
    if os.environ.get(KEY_FILE_ENV) or os.environ.get(LEGACY_KEY_FILE_ENV) or os.environ.get('THEMERR_DOCKER'):
        return
    for service in (
        SERVICE,
        Names.legacy_name,
    ):
        try:
            keyring.delete_password(service, client_id)
        except PasswordDeleteError:
            pass
        except Exception as exc:
            raise TokenStorageError(STORE_UNAVAILABLE) from exc


def _namespace(client_id: str) -> str:
    """Choose a separate encrypted slot for a server credential."""
    return (
        f':{client_id}'
        if client_id.startswith(
            (
                'server:',
                'jellyfin:',
            )
        )
        else ''
    )


def _settings_cipher(create: bool = False) -> Fernet:
    """Use the external key or a small encryption key in the desktop vault."""
    cipher = _cipher()
    if cipher is not None:
        return cipher
    try:
        with _settings_lock:
            key = keyring.get_password(SERVICE, _SETTINGS_KEY)
            if not key and create:
                key = Fernet.generate_key().decode('ascii')
                keyring.set_password(SERVICE, _SETTINGS_KEY, key)
        if not key:
            raise TokenStorageError('The configuration encryption key is unavailable.')
        return Fernet(key.encode('ascii'))
    except TokenStorageError:
        raise
    except Exception as exc:
        raise TokenStorageError(STORE_UNAVAILABLE) from exc


def encrypt_setting(value: str) -> str:
    """Encrypt a setting without putting large cookie exports in the OS vault.

    Parameters
    ----------
    value : str
        Plaintext setting.

    Returns
    -------
    str
        Versioned Fernet ciphertext.
    """
    ciphertext = _settings_cipher(create=True).encrypt(value.encode('utf-8')).decode('ascii')
    return f'{SETTING_PREFIX}{ciphertext}'


def decrypt_setting(value: str) -> str:
    """Decrypt a setting using the configured secure key storage.

    Parameters
    ----------
    value : str
        Versioned Fernet ciphertext, or an empty setting.

    Returns
    -------
    str
        Plaintext setting.

    Raises
    ------
    TokenStorageError
        The key is unavailable or the ciphertext is invalid.
    """
    if not value:
        return ''
    if not value.startswith(SETTING_PREFIX):
        raise TokenStorageError('The configuration setting is not encrypted.')
    try:
        return _settings_cipher().decrypt(value[len(SETTING_PREFIX):].encode('ascii')).decode('utf-8')
    except (
        InvalidToken,
        UnicodeError,
    ) as exc:
        raise TokenStorageError('Unable to decrypt the configuration setting with the current key.') from exc
