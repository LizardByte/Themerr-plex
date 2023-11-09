# -*- coding: utf-8 -*-

# plex debugging
try:
    import plexhints  # noqa: F401
except ImportError:
    pass
else:  # the code is running outside of Plex
    from plexhints.log_kit import Log  # log kit
    from plexhints.parse_kit import JSON  # parse kit

# local imports
from constants import canonical_db

# imports from Libraries\Shared
from typing import Union

database_cache = {}


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
        try:
            pages = JSON.ObjectFromURL(
                cacheTime=3600,
                url='https://app.lizardbyte.dev/ThemerrDB/{}/pages.json'.format(database_type),
                errors='ignore'  # don't crash the plugin
            )
            page_count = pages['pages']

            id_index = set()

            for page in range(page_count):
                page_data = JSON.ObjectFromURL(
                    cacheTime=3600,
                    url='https://app.lizardbyte.dev/ThemerrDB/{}/all_page_{}.json'.format(database_type, page + 1),
                    errors='ignore'  # don't crash the plugin
                )

                id_index.update(str(item['id']) for item in page_data)

            database_cache[database_type] = id_index
            Log.Info('{}: {} items in database'.format(database_type, len(id_index)))
        except Exception as e:
            Log.Error('{}: Error retrieving page index from ThemerrDB: {}'.format(database_type, e))


def item_may_exist(database_type, database, id):
    # type: (str, str, Union[int, str]) -> bool
    """
    Check if an item may exist in the ThemerrDB.

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
        True if the item exists in the ThemerrDB (or if the cache is empty/missing), otherwise False.
    """
    if database != canonical_db[database_type]:
        return True

    if database_type in database_cache:
        return str(id) in database_cache[database_type]

    return True
