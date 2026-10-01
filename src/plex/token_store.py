"""Store Plex account tokens outside plaintext application data."""

# standard imports
import os
from pathlib import Path

# lib imports
from cryptography.fernet import Fernet, InvalidToken
import keyring
from keyring.errors import PasswordDeleteError

# local imports
from themerr import storage


SERVICE = 'Themerr-plex'
KEY_FILE_ENV = 'THEMERR_PLEX_TOKEN_KEY_FILE'


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
    key_path = os.environ.get(KEY_FILE_ENV)
    if key_path:
        try:
            return Fernet(Path(key_path).read_bytes().strip())
        except (OSError, ValueError) as exc:
            raise TokenStorageError(f'Unable to read a valid Plex token key from {KEY_FILE_ENV}.') from exc
    if os.environ.get('THEMERR_DOCKER'):
        raise TokenStorageError(f'Set {KEY_FILE_ENV} to a mounted secret before signing in to Plex.')
    return None


def get_token(client_id: str) -> str:
    """Read a token from the selected secure store.

    Parameters
    ----------
    client_id : str
        Installation's Plex OAuth client identifier.

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
        except (InvalidToken, UnicodeError) as exc:
            raise TokenStorageError('The Plex token key does not match the stored token.') from exc
    try:
        return keyring.get_password(SERVICE, client_id) or ''
    # Native backends can raise errors outside keyring's exception hierarchy.
    except Exception as exc:
        raise TokenStorageError('The OS credential store is unavailable.') from exc


def save_token(client_id: str, token: str) -> None:
    """Persist a Plex token without storing plaintext in SQLite.

    Parameters
    ----------
    client_id : str
        Installation's Plex OAuth client identifier.
    token : str
        Plex account token.
    """
    cipher = _cipher()
    if cipher is not None:
        storage.save_encrypted_token(cipher.encrypt(token.encode('utf-8')).decode('ascii'), _namespace(client_id))
        return
    try:
        keyring.set_password(SERVICE, client_id, token)
    except Exception as exc:
        raise TokenStorageError('The OS credential store is unavailable.') from exc


def delete_token(client_id: str) -> None:
    """Remove this installation's saved Plex token.

    Parameters
    ----------
    client_id : str
        Installation's Plex OAuth client identifier.
    """
    storage.save_encrypted_token(None, _namespace(client_id))
    if os.environ.get(KEY_FILE_ENV) or os.environ.get('THEMERR_DOCKER'):
        return
    try:
        keyring.delete_password(SERVICE, client_id)
    except PasswordDeleteError:
        pass
    except Exception as exc:
        raise TokenStorageError('The OS credential store is unavailable.') from exc


def _namespace(client_id: str) -> str:
    """Choose a separate encrypted slot for a server credential."""
    return ':' + client_id if client_id.startswith('server:') else ''
