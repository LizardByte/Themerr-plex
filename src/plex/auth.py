"""Plex PIN sign-in and local storage for the resulting account token."""

# standard imports
import json
import os
import tempfile
import threading
import uuid
from urllib.parse import urlencode

# lib imports
import requests

# local imports
from common import config
from common import logger


PLEX_PIN_URL = 'https://plex.tv/api/v2/pins'
PLEX_AUTH_URL = 'https://app.plex.tv/auth#?'
PRODUCT = 'Themerr-plex'
TIMEOUT = 10
_lock = threading.RLock()


def _credentials_path() -> str:
    """Return the credentials path next to the active configuration file.

    Returns
    -------
    str
        Credentials file path.
    """
    return os.path.join(os.path.dirname(os.path.abspath(config.CONFIG.filename)), 'plex-auth.json')


def _load() -> dict:
    """Read locally saved Plex credentials.

    Returns
    -------
    dict
        Saved client identifier and token, if available.
    """
    try:
        with open(_credentials_path(), encoding='utf-8') as credentials_file:
            credentials = json.load(credentials_file)
        return credentials if isinstance(credentials, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(credentials: dict) -> None:
    """Atomically store Plex credentials with owner-only permissions on Unix.

    Parameters
    ----------
    credentials : dict
        Client identifier and optional account token.
    """
    path = _credentials_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=os.path.dirname(path),
                                         prefix='.plex-auth-', delete=False) as credentials_file:
            temporary_path = credentials_file.name
            os.chmod(temporary_path, 0o600)
            json.dump(credentials, credentials_file)
        os.replace(temporary_path, path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def get_token() -> str:
    """Get the token issued by Plex during sign-in.

    Returns
    -------
    str
        Saved token, or an empty string if disconnected.
    """
    with _lock:
        token = _load().get('token', '')
        if token:
            logger.blacklist_config({'Plex': {'PLEX_TOKEN': token}})
        return token


def set_token(token: str) -> None:
    """Save the token returned by a completed Plex PIN login.

    Parameters
    ----------
    token : str
        Plex account token.
    """
    with _lock:
        credentials = _load()
        credentials['token'] = token
        _save(credentials)
        logger.blacklist_config({'Plex': {'PLEX_TOKEN': token}})


def disconnect() -> None:
    """Remove the saved token while retaining the client identifier."""
    with _lock:
        credentials = _load()
        credentials.pop('token', None)
        _save(credentials)


def _client_identifier() -> str:
    """Return a stable identifier for this installation.

    Returns
    -------
    str
        Client identifier.
    """
    with _lock:
        credentials = _load()
        if not credentials.get('client_id'):
            credentials['client_id'] = uuid.uuid4().hex
            _save(credentials)
        return credentials['client_id']


def _headers(client_id: str) -> dict:
    """Build headers for Plex account API requests.

    Parameters
    ----------
    client_id : str
        This installation's client identifier.

    Returns
    -------
    dict
        Plex API headers.
    """
    return {'Accept': 'application/json', 'X-Plex-Product': PRODUCT,
            'X-Plex-Client-Identifier': client_id}


def start_login() -> dict:
    """Create a PIN and URL for browser-based Plex sign-in.

    Returns
    -------
    dict
        PIN identifier, code, and Plex sign-in URL.
    """
    client_id = _client_identifier()
    response = requests.post(PLEX_PIN_URL, headers=_headers(client_id), data={'strong': 'true'}, timeout=TIMEOUT)
    response.raise_for_status()
    pin = response.json()
    pin_id, code = pin['id'], pin['code']
    if not isinstance(pin_id, int) or not isinstance(code, str) or not code:
        raise ValueError('Invalid PIN response from Plex')
    query = urlencode({'clientID': client_id, 'code': code, 'context[device][product]': PRODUCT})
    return {'pin_id': pin_id, 'code': code, 'auth_url': PLEX_AUTH_URL + query}


def check_login(pin_id: int, code: str) -> str:
    """Check whether the user claimed a Plex PIN.

    Parameters
    ----------
    pin_id : int
        PIN identifier from ``start_login``.
    code : str
        PIN code from ``start_login``.

    Returns
    -------
    str
        Plex token, or an empty string while authentication is pending.
    """
    response = requests.get(f'{PLEX_PIN_URL}/{pin_id}', headers=_headers(_client_identifier()),
                            params={'code': code}, timeout=TIMEOUT)
    response.raise_for_status()
    token = response.json().get('authToken') or ''
    if token:
        logger.blacklist_config({'Plex': {'PLEX_TOKEN': token}})
    return token
