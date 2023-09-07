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


def get_tmdb_id_from_imdb_id(imdb_id):
    # type: (str) -> Optional[int]
    """
    Convert IMDB ID to TMDB ID.

    Use the builtin Plex tmdb api service to search for a movie by IMDB ID.

    Parameters
    ----------
    imdb_id : str
        IMDB ID to convert.

    Returns
    -------
    Optional[int]
        Return TMDB ID if found, otherwise None.

    Examples
    --------
    >>> get_tmdb_id_from_imdb_id(imdb_id='tt1254207')
    10378
    """
    # according to https://www.themoviedb.org/talk/5f6a0500688cd000351c1712 we can search by imdb id
    # https://api.themoviedb.org/3/find/tt0458290?api_key=###&external_source=imdb_id
    find_imdb_item = 'find/{}?external_source=imdb_id'

    url = '{}/{}'.format(tmdb_base_url, find_imdb_item.format(String.Quote(s=imdb_id, usePlus=True)))
    try:
        tmdb_data = JSON.ObjectFromURL(
            url=url, sleep=2.0, headers=dict(Accept='application/json'), cacheTime=CACHE_1DAY, errors='strict')
    except Exception as e:
        Log.Debug('Error converting IMDB ID to TMDB ID: {}'.format(e))
    else:
        Log.Debug('TMDB data: {}'.format(tmdb_data))
        try:
            tmdb_id = int(tmdb_data['movie_results'][0]['id'])  # this is already an integer, but let's force it
        except (IndexError, KeyError, ValueError):
            Log.Debug('Error converting IMDB ID to TMDB ID: {}'.format(tmdb_data))
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
