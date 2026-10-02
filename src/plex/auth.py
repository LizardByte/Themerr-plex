"""Plex PIN sign-in with secure storage for the resulting account token."""

# standard imports
import threading
import uuid
from urllib.parse import urlencode

# lib imports
import requests

# local imports
from common.definitions import Names
from common import logger
from plex import token_store
from themerr import storage


PLEX_PIN_URL = 'https://plex.tv/api/v2/pins'
PLEX_AUTH_URL = 'https://app.plex.tv/auth#?'
PRODUCT = Names.name
TIMEOUT = 10
_lock = threading.RLock()
log = logger.get_logger(__name__)


def _load() -> dict:
    """Read locally saved Plex credentials.

    Returns
    -------
    dict
        Saved client identifier, if available.
    """
    return storage.get_credentials()


def _save(credentials: dict) -> None:
    """Store the non-secret Plex client identifier in SQLite.

    Parameters
    ----------
    credentials : dict
        Client identifier.
    """
    storage.save_credentials(credentials)


def get_token() -> str:
    """Get the token issued by Plex during sign-in.

    Returns
    -------
    str
        Saved token, or an empty string if disconnected.
    """
    with _lock:
        client_id = _load().get('client_id')
        if not client_id:
            return ''
        try:
            token = token_store.get_token(client_id)
        except token_store.TokenStorageError as exc:
            log.warning('%s', exc)
            return ''
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
        token_store.save_token(_client_identifier(), token)
        logger.blacklist_config({'Plex': {'PLEX_TOKEN': token}})


def disconnect() -> None:
    """Remove the saved token while retaining the client identifier."""
    with _lock:
        client_id = _load().get('client_id')
        if client_id:
            token_store.delete_token(client_id)


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
