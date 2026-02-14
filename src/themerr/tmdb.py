# standard imports
from typing import Optional, Union

# local imports
from common import config
from common import helpers
from common import logger

log = logger.get_logger(name=__name__)


def tmdb_base_url() -> Optional[str]:
    """
    Get the base URL for the Plex TMDB service.

    .. todo:: is Plex going to keep these services after removing plugins altogether?

    Returns
    -------
    str
        Base URL for the Plex TMDB service.

    Examples
    --------
    >>> tmdb_base_url()
    '.../services/tmdb?uri='
    """
    try:
        return f'{config.CONFIG['Plex']['PLEX_URL']}/services/tmdb?uri='
    except (KeyError, TypeError):
        log.exception('Error getting base URL for Plex TMDB service. Config may not be initialized.')
        return


def get_tmdb_id_from_external_id(external_id: Union[int, str], database: str, item_type: str) -> Optional[int]:
    """
    Convert IMDB ID to TMDB ID.

    Use the builtin Plex tmdb api service to search for a movie by IMDB ID.

    Parameters
    ----------
    external_id : Union[int, str]
        External ID to convert.
    database : str
        Database to search. Must be one of 'imdb' or 'tvdb'.
    item_type : str
        Item type to search. Must be one of 'movie' or 'tv'.

    Returns
    -------
    Optional[int]
        Return TMDB ID if found, otherwise None.

    Examples
    --------
    >>> get_tmdb_id_from_external_id(imdb_id='tt1254207', database='imdb', item_type='movie')
    10378
    >>> get_tmdb_id_from_external_id(imdb_id='268592', database='tvdb', item_type='tv')
    48866
    """
    if database.lower() not in ['imdb', 'tvdb']:
        log.exception(f'Invalid database: {database}')
        return
    if item_type.lower() not in ['movie', 'tv']:
        log.exception(f'Invalid item type: {item_type}')
        return

    # according to https://www.themoviedb.org/talk/5f6a0500688cd000351c1712 we can search by external id
    # https://api.themoviedb.org/3/find/tt0458290?api_key=###&external_source=imdb_id
    find_url_suffix = 'find/{}?external_source={}_id'

    url = f'{tmdb_base_url()}/{find_url_suffix.format(
        helpers.string_quote(string=str(external_id), use_plus=True), database.lower())}'
    try:
        tmdb_data = helpers.json_get(
            url=url,
            sleep_time=2.0,
            headers=dict(Accept='application/json'),
            cache_time=86400,  # 1 day
        )
    except Exception as e:
        log.debug(f'Error converting external ID to TMDB ID: {e}')
    else:
        log.debug(f'TMDB data: {tmdb_data}')
        try:
            # this is already an integer, but let's force it
            tmdb_id = int(tmdb_data[f'{item_type.lower()}_results'][0]['id'])
        except (IndexError, KeyError, ValueError):
            log.debug(f'Error converting external ID to TMDB ID: {tmdb_data}')
        else:
            return tmdb_id


def get_tmdb_id_from_collection(search_query: str) -> Optional[int]:
    """
    Search for a collection by name.

    Use the builtin Plex tmdb api service to search for a tmdb collection by name.

    Parameters
    ----------
    search_query : str
        Name of collection to search for.

    Returns
    -------
    Optional[int]
        Return collection ID if found, otherwise None.

    Examples
    --------
    >>> get_tmdb_id_from_collection(search_query='James Bond Collection')
    645
    >>> get_tmdb_id_from_collection(search_query='James Bond')
    645
    """
    # /search/collection?query=James%20Bond%20Collection&include_adult=false&language=en-US&page=1"
    query_url = 'search/collection?query={}'
    query_item = search_query.split('&', 1)[0]

    # Plex returns 500 error if spaces are in the collection query, same with `_`, `+`, and `%20`... so use `-`
    url = f'{tmdb_base_url()}/{query_url.format(helpers.string_quote(
        string=search_query.replace(' ', '-'), use_plus=False))}'
    try:
        tmdb_data = helpers.json_get(
            url=url,
            sleep_time=2.0,
            headers=dict(Accept='application/json'),
            cache_time=86400,  # 1 day
        )
    except Exception as e:
        log.debug(f'Error searching for collection {search_query}: {e}')
    else:
        collection_id = None
        log.debug(f'TMDB data: {tmdb_data}')

        end_string = 'Collection'  # collection names on themoviedb end with 'Collection'
        try:
            for result in tmdb_data['results']:
                if result['name'].lower() == query_item.lower() or \
                        f'{query_item.lower()} {end_string}'.lower() == result['name'].lower():
                    collection_id = int(result['id'])
        except (IndexError, KeyError, ValueError):
            log.debug(f'Error searching for collection {search_query}: {tmdb_data}')
        else:
            return collection_id
