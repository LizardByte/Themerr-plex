# standard imports
import json
import os
from threading import Lock

# lib imports
from urllib.parse import quote_plus

# local imports
from common import config
from common import definitions
from common import helpers
from common import logger
from themerr.constants import contributes_to, issue_urls
from themerr import general
from plex.plexapi import PLEX_SETUP_ERROR, get_database_info, setup_plexapi
from themerr import themerr_db
from themerr import tmdb

log = logger.get_logger(name=__name__)

# where the database cache is stored
database_cache_file = os.path.join(definitions.Paths.CONFIG_DIR, 'database_cache.json')
database_cache_lock = Lock()


def _item_issue_url(item, database_type: str, database_id: str | None, year: int | None) -> str | None:
    """Build the ThemerrDB issue link for an item.

    Parameters
    ----------
    item : PlexPartialObject
        Plex media or collection.
    database_type : str
        ThemerrDB database type.
    database_id : str or None
        External database identifier.
    year : int or None
        Release year.

    Returns
    -------
    str or None
        Encoded issue URL when supported.
    """
    issue_url = issue_urls.get(database_type)
    if not issue_url or not database_id:
        return None
    if item.type == 'movie':
        issue_title = f'{getattr(item, "originalTitle", None) or item.title} ({year})'
    elif item.type == 'show':
        issue_title = f'{item.title} ({year})'
    else:
        issue_title = item.title
    return issue_url.format(quote_plus(issue_title), database_id)


def _cache_item(item) -> dict:
    """Convert one Plex item to dashboard data.

    Parameters
    ----------
    item : PlexPartialObject
        Plex media or collection.

    Returns
    -------
    dict
        Dashboard fields for the item.
    """
    database_type, database, item_agent, database_id = get_database_info(item=item)
    original_id = database_id
    year = getattr(item, 'year', None)
    if item.type == 'movie' and database_id and (
            item_agent == 'com.plexapp.agents.imdb' or database_id.startswith('tt')
    ):
        database_id = tmdb.get_tmdb_id_from_external_id(
            external_id=database_id, database='imdb', item_type='movie') or None

    exists = bool(database_type and database and original_id and themerr_db.item_exists(
        database_type=database_type, database=database, id=original_id,
    ))
    issue_action = 'edit' if exists else 'add'
    if item.theme:
        theme_status = 'complete'
    elif exists:
        theme_status = 'failed'
    else:
        theme_status = 'missing'

    return {
        'rating_key': str(item.ratingKey),
        'title': item.title,
        'agent': item_agent,
        'database': database,
        'database_type': database_type,
        'database_id': database_id,
        'issue_action': issue_action,
        'issue_url': _item_issue_url(item, database_type, database_id, year),
        'theme': bool(item.theme),
        'theme_provider': general.get_theme_provider(item=item),
        'theme_status': theme_status,
        'type': item.type,
        'year': year,
    }


def _section_media_items(section) -> list:
    """Select media matched by supported Plex agents in a library section.

    Parameters
    ----------
    section : LibrarySection
        Plex library section.

    Returns
    -------
    list
        Media with a supported agent.
    """
    if section.agent in contributes_to:
        return section.all()
    if section.type not in ('movie', 'show'):
        return []
    guid_prefix = f'plex://{section.type}/'
    return [item for item in section.all() if (getattr(item, 'guid', None) or '').startswith(guid_prefix)]


def _cache_section(section) -> dict:
    """Collect dashboard counts and item details for a Plex section.

    Parameters
    ----------
    section : LibrarySection
        Plex library section.

    Returns
    -------
    dict
        Dashboard data for the section.
    """
    media_items = _section_media_items(section)
    if section.agent in contributes_to:
        media_items_with_themes = section.all(theme__exists=True)
    else:
        media_items_with_themes = [item for item in media_items if item.theme]
    collections_enabled = (
        config.CONFIG['Themerr']['BOOL_PLEX_COLLECTION_SUPPORT'] and section.agent in contributes_to
    )
    collections = section.collections() if collections_enabled else []
    collections_with_themes = section.collections(theme__exists=True) if collections_enabled else []
    all_items = media_items + collections

    return {
        'key': section.key,
        'title': section.title,
        'agent': section.agent,
        'items': [_cache_item(item) for item in all_items],
        'media_count': len(media_items),
        'media_percent_complete': int(len(media_items_with_themes) / len(media_items) * 100)
        if media_items_with_themes else 0,
        'collection_count': len(collections),
        'collection_percent_complete': int(len(collections_with_themes) / len(collections) * 100)
        if collections_with_themes else 0,
        'collections_enabled': collections_enabled,
        'total_count': len(all_items),
        'type': section.type,
    }


def cache_data() -> None:
    """
    Cache data for use in the Web UI dashboard.

    Because there are many http requests that must be made to gather the data for the dashboard, it can be
    time-consuming to populate; therefore, this is performed within this caching function, which runs on a schedule.
    This function will create a json file that can be loaded by other functions.
    """
    # get all Plex items from supported metadata agents
    plex_server = setup_plexapi()
    if not plex_server:
        log.error(PLEX_SETUP_ERROR)
        return

    plex_library = plex_server.library

    themerr_db.update_cache()

    sections = plex_library.sections()

    items = {}

    for section in sections:
        if section.agent not in contributes_to and getattr(section, 'type', None) not in ('movie', 'show'):
            continue
        section_data = _cache_section(section)
        if section.agent in contributes_to or section_data['total_count']:
            items[section.key] = section_data

    with database_cache_lock:
        helpers.file_save(filename=database_cache_file, data=json.dumps(items), binary=False)
