"""Resolve TMDB IDs from ThemerrDB, the media server, or TMDB."""

# standard imports
import os
from urllib.parse import quote

# local imports
from common import helpers, logger
from media_servers import get_backend
from themerr import storage, themerr_db


TMDB_API_URL = 'https://api.themoviedb.org/3'
log = logger.get_logger(__name__)


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

    ThemerrDB publishes IMDb IDs for movies and titles for TV shows. A server
    metadata service or an optional TMDB API token can resolve other items.

    Parameters
    ----------
    external_id : int or str
        IMDb or TVDB identifier from the media server.
    database : str
        ``imdb`` or ``tvdb``.
    item_type : str
        ``movie`` or ``tv``.
    title : str or None
        Show title, used when ThemerrDB has no external ID mapping.

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
    server = get_backend().server(storage.current_server_id())
    data = server.query_tmdb(f'find/{quote(str(external_id), safe="")}', params)
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
    """Find a collection by title in ThemerrDB, the media server, or TMDB.

    Parameters
    ----------
    search_query : str
        Collection title, with or without the ``Collection`` suffix.
    language : str or None
        Library language for the TMDB API fallback.

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
    data = get_backend().server(storage.current_server_id()).query_tmdb('search/collection', params)
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
