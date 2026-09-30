"""Resolve TMDB IDs from the already downloaded ThemerrDB index."""

# standard imports
import os

# local imports
from common import helpers
from themerr import themerr_db


TMDB_API_URL = 'https://api.themoviedb.org/3'


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

    ThemerrDB publishes IMDb IDs for movies and titles for TV shows. A configured
    TMDB API read token can resolve items absent from ThemerrDB.

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
        TMDB identifier for an item already present in ThemerrDB.
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
    data = _api_get(f'find/{external_id}', {'external_source': f'{database}_id'})
    try:
        return int(data[f'{item_type}_results'][0]['id'])
    except (IndexError, KeyError, TypeError, ValueError):
        return None


def get_tmdb_id_from_collection(search_query: str, language: str | None = None) -> int | None:
    """Find a collection by title in ThemerrDB or the optional TMDB API.

    Parameters
    ----------
    search_query : str
        Plex collection title, with or without the ``Collection`` suffix.
    language : str or None
        Plex library language for the TMDB API fallback.

    Returns
    -------
    int or None
        TMDB collection identifier when present in ThemerrDB.
    """
    database_id = themerr_db.find_id_by_title('movie_collections', search_query)
    if database_id:
        return database_id

    params = {'query': search_query}
    if language:
        params['language'] = language
    data = _api_get('search/collection', params)
    search_key = themerr_db._title_key(search_query)
    for result in data.get('results', []):
        try:
            result_key = themerr_db._title_key(result['name'])
            if result_key in (search_key, f'{search_key} collection'):
                return int(result['id'])
        except (KeyError, TypeError, ValueError):
            continue
    return None
