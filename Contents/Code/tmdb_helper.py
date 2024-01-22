# -*- coding: utf-8 -*-

# plex debugging
try:
    import plexhints  # noqa: F401
except ImportError:
    pass
else:  # the code is running outside of Plex
    from plexhints.constant_kit import CACHE_1DAY  # constant kit
    from plexhints.log_kit import Log  # log kit
    from plexhints.parse_kit import JSON  # parse kit
    from plexhints.util_kit import String  # util kit

# imports from Libraries\Shared
from typing import Optional

# url borrowed from TheMovieDB.bundle
tmdb_base_url = 'http://127.0.0.1:32400/services/tmdb?uri='


def get_tmdb_id_from_external_id(external_id, database, item_type):
    # type: (str, str, str) -> Optional[int]
    """
    Convert IMDB ID to TMDB ID.

    Use the builtin Plex tmdb api service to search for a movie by IMDB ID.

    Parameters
    ----------
    external_id : str
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
        Log.Exception('Invalid database: {}'.format(database))
        return
    if item_type.lower() not in ['movie', 'tv']:
        Log.Exception('Invalid item type: {}'.format(item_type))
        return

    # according to https://www.themoviedb.org/talk/5f6a0500688cd000351c1712 we can search by external id
    # https://api.themoviedb.org/3/find/tt0458290?api_key=###&external_source=imdb_id
    find_imdb_item = 'find/{}?external_source={}_id'

    url = '{}/{}'.format(
        tmdb_base_url,
        find_imdb_item.format(String.Quote(s=external_id, usePlus=True), database.lower())
    )
    try:
        tmdb_data = JSON.ObjectFromURL(
            url=url, sleep=2.0, headers=dict(Accept='application/json'), cacheTime=CACHE_1DAY, errors='strict')
    except Exception as e:
        Log.Debug('Error converting external ID to TMDB ID: {}'.format(e))
    else:
        Log.Debug('TMDB data: {}'.format(tmdb_data))
        try:
            # this is already an integer, but let's force it
            tmdb_id = int(tmdb_data['{}_results'.format(item_type.lower())][0]['id'])
        except (IndexError, KeyError, ValueError):
            Log.Debug('Error converting external ID to TMDB ID: {}'.format(tmdb_data))
        else:
            return tmdb_id


def get_tmdb_id_from_collection(search_query):
    # type: (str) -> Optional[int]
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

    # Plex returns 500 error if spaces are in collection query, same with `_`, `+`, and `%20`... so use `-`
    url = '{}/{}'.format(tmdb_base_url, query_url.format(String.Quote(
        s=search_query.replace(' ', '-'), usePlus=True)))
    try:
        tmdb_data = JSON.ObjectFromURL(
            url=url, sleep=2.0, headers=dict(Accept='application/json'), cacheTime=CACHE_1DAY, errors='strict')
    except Exception as e:
        Log.Debug('Error searching for collection {}: {}'.format(search_query, e))
    else:
        collection_id = None
        Log.Debug('TMDB data: {}'.format(tmdb_data))

        end_string = 'Collection'  # collection names on themoviedb end with 'Collection'
        try:
            for result in tmdb_data['results']:
                if result['name'].lower() == search_query.lower() or \
                        '{} {}'.format(search_query.lower(), end_string).lower() == result['name'].lower():
                    collection_id = int(result['id'])
        except (IndexError, KeyError, ValueError):
            Log.Debug('Error searching for collection {}: {}'.format(search_query, tmdb_data))
        else:
            return collection_id
