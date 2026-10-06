"""Credentialed, server-scoped access to Plex's TMDB proxy."""

# standard imports
from threading import Lock
from time import monotonic
from urllib.parse import quote, urlencode

# lib imports
import requests

# local imports
from common import config, logger
from plex import auth, servers, token_store
from themerr import storage

PROXY_TIMEOUT = 10
PROXY_CACHE_SECONDS = 86400
_proxy_cache: dict[tuple[str, ...], tuple[float, dict]] = {}
_proxy_lock = Lock()
log = logger.get_logger(__name__)


def query(path: str, params: dict) -> dict:
    """Query the Plex server's TMDB service without persisting its token.

    Parameters
    ----------
    path : str
        TMDB service path.
    params : dict
        TMDB service query parameters.

    Returns
    -------
    dict
        JSON response, or an empty dictionary if the proxy is unavailable.
    """
    if path == 'search/collection' and isinstance(params.get('query'), str):
        params = {
            **params,
            'query': params['query'].replace(' ', '-'),
        }
    try:
        server_id = storage.current_server_id()
        record = servers.get_server(server_id) if server_id != 'default' else None
        if server_id != 'default' and (record is None or not record['enabled']):
            return {}
        base_url = (record['url'] if record else config.CONFIG['Plex']['PLEX_URL']).rstrip('/')
    except (
        KeyError,
        TypeError,
        AttributeError,
    ):
        return {}
    if not base_url:
        return {}
    uri = f'/{path}?{urlencode(params, quote_via=quote)}'
    key = (
        server_id,
        base_url,
        uri,
    )
    with _proxy_lock:
        cached = _proxy_cache.get(key)
        if cached and cached[0] > monotonic():
            return cached[1]
    token = token_store.get_token(servers.credential_id(server_id)) if record else auth.get_token()
    if not token:
        return {}
    data = _request_json(base_url, token, uri)
    if data is None:
        return {}
    with _proxy_lock:
        if len(_proxy_cache) >= 2048:
            _proxy_cache.clear()
        _proxy_cache[key] = (
            monotonic() + PROXY_CACHE_SECONDS,
            data,
        )
    return data


def _request_json(base_url: str, token: str, uri: str) -> dict | None:
    """Return valid proxy JSON, distinguishing an empty result from a failed request."""
    try:
        response = requests.get(
            f'{base_url}/services/tmdb',
            params={'uri': uri},
            headers={
                'X-Plex-Token': token,
                'Accept': 'application/json',
            },
            timeout=PROXY_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except (
        requests.RequestException,
        ValueError,
    ) as exc:
        log.debug('Plex TMDB lookup failed: %s', exc)
        return None
    return data if isinstance(data, dict) else None
