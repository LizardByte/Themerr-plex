"""Resolve TMDB IDs from ThemerrDB, Plex's TMDB proxy, or TMDB."""

# standard imports
import os
from threading import Lock
from time import monotonic
from urllib.parse import quote, urlencode

# lib imports
import requests

# local imports
from common import config, helpers, logger
from plex import auth
from themerr import themerr_db


TMDB_API_URL = 'https://api.themoviedb.org/3'
PROXY_TIMEOUT = 10
PROXY_CACHE_SECONDS = 86400
_proxy_cache: dict[tuple[str, str], tuple[float, dict]] = {}
_proxy_lock = Lock()
log = logger.get_logger(__name__)


def _plex_get(path: str, params: dict) -> dict:
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
    try:
        base_url = config.CONFIG['Plex']['PLEX_URL'].rstrip('/')
    except (KeyError, TypeError, AttributeError):
        return {}
    if not base_url:
        return {}
    uri = f'/{path}?{urlencode(params, quote_via=quote)}'
    key = (base_url, uri)
    with _proxy_lock:
        cached = _proxy_cache.get(key)
        if cached and cached[0] > monotonic():
            return cached[1]
    token = auth.get_token()
    if not token:
        return {}
    try:
        response = requests.get(f'{base_url}/services/tmdb', params={'uri': uri},
                                headers={'X-Plex-Token': token, 'Accept': 'application/json'},
                                timeout=PROXY_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        log.debug('Plex TMDB lookup failed: %s', exc)
        return {}
    if not isinstance(data, dict):
        return {}
    with _proxy_lock:
        if len(_proxy_cache) >= 2048:
            _proxy_cache.clear()
        _proxy_cache[key] = (monotonic() + PROXY_CACHE_SECONDS, data)
    return data


def _api_get(path: str, params: dict) -> dict:
    """Query TMDB when an optional API read token is configured.

    Parameters
    ----------
    path : str
        TMDB API path.
    params : dict
        Query parameters.

    Returns
    -------
    dict
        JSON response, or an empty dictionary without a token.
    """
    token = os.environ.get('TMDB_API_READ_ACCESS_TOKEN')
    if not token:
        return {}
    data = helpers.json_get(
        url=f'{TMDB_API_URL}/{path}', params=params,
        headers={'Accept': 'application/json', 'Authorization': f'Bearer {token}'},
        cache_time=86400,
    )
    return data if isinstance(data, dict) else {}


def get_tmdb_id_from_external_id(external_id: int | str, database: str, item_type: str,
                                 title: str | None = None) -> int | None:
    """Resolve an external movie or show identifier to a TMDB ID.

    ThemerrDB publishes IMDb IDs for movies and titles for TV shows. The Plex
    proxy or an optional TMDB API token can resolve other items.

    Parameters
    ----------
    external_id : int or str
        IMDb or TVDB identifier from Plex.
    database : str
        ``imdb`` or ``tvdb``.
    item_type : str
        ``movie`` or ``tv``.
    title : str or None
        Plex show title, used when ThemerrDB has no external ID mapping.

    Returns
    -------
    int or None
        Resolved TMDB identifier, when available.
    """
    if database not in ('imdb', 'tvdb') or item_type not in ('movie', 'tv'):
        return None
    if item_type == 'movie' and database == 'imdb':
        database_id = themerr_db.find_movie_id_by_imdb(str(external_id))
        if database_id:
            return database_id
    if item_type == 'tv' and title:
        database_id = themerr_db.find_id_by_title('tv_shows', title)
        if database_id:
            return database_id

    if item_type == 'movie' and database == 'tvdb':
        return None  # TMDB's find endpoint does not support TVDB IDs for movies.
    params = {'external_source': f'{database}_id'}
    data = _plex_get(f'find/{quote(str(external_id), safe="")}', params)
    try:
        return int(data[f'{item_type}_results'][0]['id'])
    except (IndexError, KeyError, TypeError, ValueError):
        pass
    data = _api_get(f'find/{external_id}', params)
    try:
        return int(data[f'{item_type}_results'][0]['id'])
    except (IndexError, KeyError, TypeError, ValueError):
        return None


def get_tmdb_id_from_collection(search_query: str, language: str | None = None) -> int | None:
    """Find a collection by title in ThemerrDB, Plex, or TMDB.

    Parameters
    ----------
    search_query : str
        Plex collection title, with or without the ``Collection`` suffix.
    language : str or None
        Plex library language for the TMDB API fallback.

    Returns
    -------
    int or None
        Resolved TMDB collection identifier, when available.
    """
    database_id = themerr_db.find_id_by_title('movie_collections', search_query)
    if database_id:
        return database_id

    params = {'query': search_query}
    if language:
        params['language'] = language
    search_key = themerr_db._title_key(search_query)
    # Plex's proxy rejects spaces in collection searches; hyphens work.
    proxy_params = {**params, 'query': search_query.replace(' ', '-')}
    data = _plex_get('search/collection', proxy_params)
    for result in data.get('results', []):
        try:
            result_key = themerr_db._title_key(result['name'])
            if result_key in (search_key, f'{search_key} collection'):
                return int(result['id'])
        except (KeyError, TypeError, ValueError):
            continue
    data = _api_get('search/collection', params)
    for result in data.get('results', []):
        try:
            result_key = themerr_db._title_key(result['name'])
            if result_key in (search_key, f'{search_key} collection'):
                return int(result['id'])
        except (KeyError, TypeError, ValueError):
            continue
    return None
