# -*- coding: utf-8 -*-

# plex debugging
try:
    import plexhints  # noqa: F401
except ImportError:
    pass
else:  # the code is running outside of Plex
    from plexhints.log_kit import Log  # log kit
    from plexhints.parse_kit import JSON  # parse kit

# imports from Libraries\Shared
from typing import Union

database_cache = {}

db_field_name = dict(
    games={'igdb': 'id'},
    game_collections={'igdb': 'id'},
    game_franchises={'igdb': 'id'},
    movies={'themoviedb': 'id', 'imdb': 'imdb_id'},
    movie_collections={'themoviedb': 'id'},
)


def update_cache():
    # type: () -> None
    """
    Update the ThemerrDB cache.

    The pages.json file is fetched for all database types, then each all_page_N.json file is fetched to form the 
    complete set of available IDs.

    Note: the cache only contains IDs for each database type's canonical database (see constants.canonical_db).
    """
    Log.Info('Updating ThemerrDB cache')

    global database_cache
    database_types = canonical_db.keys()

    for database_type in database_types:
        databases = db_field_name[database_type]
        try:
            pages = JSON.ObjectFromURL(
                cacheTime=3600,
                url='https://app.lizardbyte.dev/ThemerrDB/{}/pages.json'.format(database_type),
                errors='ignore'  # don't crash the plugin
            )
            page_count = pages['pages']

            id_index = {db: set() for db in databases}

            for page in range(page_count):
                page_data = JSON.ObjectFromURL(
                    cacheTime=3600,
                    url='https://app.lizardbyte.dev/ThemerrDB/{}/all_page_{}.json'.format(database_type, page + 1),
                    errors='ignore'  # don't crash the plugin
                )

                for db in databases:
                    id_index[db].update(str(item[db_field_name[database_type][db]]) for item in page_data)

            database_cache[database_type] = id_index
            Log.Info('{}: database updated'.format(database_type, len(id_index)))
        except Exception as e:
            Log.Error('{}: Error retrieving page index from ThemerrDB: {}'.format(database_type, e))


def item_exists(database_type, database, id):
    # type: (str, str, Union[int, str]) -> bool
    """
    Check if an item exists in the ThemerrDB.

    Parameters
    ----------
    database_type : str
        The type of database to check for the item.

    database : str
        The database to check for the item.

    id : Union[int, str]
        The ID of the item to check for.

    Returns
    -------
    bool
        True if the item exists in the ThemerrDB, otherwise False.

    Examples
    --------
    >>> item_exists(database_type='games', database='igdb', id=1234)
    True

    >>> item_exists(database_type='movies', database='themoviedb', id=1234)
    False
    """
    if not database_type in database_cache:
        update_cache()

    type_cache = database_cache[database_type]
    return database in type_cache and str(id) in type_cache[database]
