# standard imports
from threading import Lock
import time
from typing import Union

# local imports
from common import helpers
from common import logger

log = logger.get_logger(name=__name__)

database_cache = {}
last_cache_update = 0

db_field_name = dict(
    movies={'themoviedb': 'id', 'imdb': 'imdb_id'},
    movie_collections={'themoviedb': 'id'},
    tv_shows={'themoviedb': 'id'},
)

lock = Lock()


def update_cache() -> None:
    """
    Update the ThemerrDB cache.

    The pages.json file is fetched for all database types, then each all_page_N.json file is fetched to form the
    complete set of available IDs.

    Attempting to update the cache while an update is already in progress will wait until the current update is
    complete.

    Updating the cache less than an hour after the last update is a no-op.
    """
    log.info('Updating ThemerrDB cache')

    global last_cache_update

    if time.time() - last_cache_update < 3600:
        log.info('Cache updated less than an hour ago, skipping')
        return

    with lock:
        for database_type, databases in db_field_name.items():
            try:
                pages = helpers.json_get(
                    cache_time=3600,
                    url=f'https://app.lizardbyte.dev/ThemerrDB/{database_type}/pages.json',
                )
                page_count = pages['pages']

                id_index = {db: set() for db in databases}

                for page in range(page_count):
                    page_data = helpers.json_get(
                        cache_time=3600,
                        url=f'https://app.lizardbyte.dev/ThemerrDB/{database_type}/all_page_{page + 1}.json',
                    )

                    for db in databases:
                        id_index[db].update(str(item[db_field_name[database_type][db]]) for item in page_data)

                database_cache[database_type] = id_index

                log.info(f'{database_type}: database updated')
            except Exception as e:
                log.error(f'{database_type}: Error retrieving page index from ThemerrDB: {e}')

                database_cache[database_type] = {}

        last_cache_update = time.time()


def item_exists(database_type: str, database: str, id: Union[int, str]) -> bool:
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
    py:class:`bool`
        True if the item exists in the ThemerrDB, otherwise False.

    Examples
    --------
    >>> item_exists(database_type='movies', database='themoviedb', id=1234)
    False
    """
    if database_type not in db_field_name:
        log.critical(f'"{database_type}" is not a valid database_type. Allowed values are: {db_field_name.keys()}')
        return False

    if database_type not in database_cache:
        update_cache()

    type_cache = database_cache[database_type]
    return database in type_cache and str(id) in type_cache[database]
