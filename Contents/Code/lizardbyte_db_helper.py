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
from typing import Optional, Tuple

collection_types = dict(
    game_collections=dict(
        db_base_url='https://db.lizardbyte.dev/collections'
    ),
    game_franchises=dict(
        db_base_url='https://db.lizardbyte.dev/franchises'
    ),
)


def get_igdb_id_from_collection(search_query, collection_type=None):
    # type: (str, Optional[str]) -> Optional[Tuple[int, str]]
    """
    Search for a collection by name.

    Match a collection by name against the LizardByte db (clone of IGDB), to get the collection ID.

    Parameters
    ----------
    search_query : str
        Collection name to search for.
    collection_type : Optional[str]
        Collection type to search for. Valid values are 'game_collections' and 'game_franchises'. If not provided, will
        first search for 'game_collections', then 'game_franchises', returning the first match.

    Returns
    -------
    Optional[Tuple[int, str]]
        Tuple of ``id`` and ``collection_type`` if found, otherwise None.

    Examples
    --------
    >>> get_igdb_id_from_collection(search_query='James Bond', collection_type='game_collections')
    326
    >>> get_igdb_id_from_collection(search_query='James Bond', collection_type='game_franchises')
    37
    """
    Log.Debug('Searching LizardByte db for collection: {}'.format(search_query))

    if collection_type is None:
        collection_types_list = ['game_collections', 'game_franchises']
    else:
        collection_types_list = [collection_type]

    for collection_type in collection_types_list:
        try:
            db_base_url = collection_types[collection_type]['db_base_url']
        except KeyError:
            Log.Error('Invalid collection type: {}'.format(collection_type))
        else:
            url = '{}/all.json'.format(db_base_url)
            try:
                collection_data = JSON.ObjectFromURL(url=url, headers=dict(Accept='application/json'),
                                                     cacheTime=0, errors='strict')
            except ValueError as e:
                Log.Error('Error getting collection data: {}'.format(e))
            else:
                for _ in collection_data:
                    if search_query.lower() == collection_data[_]['name'].lower():
                        return collection_data[_]['id'], collection_type
