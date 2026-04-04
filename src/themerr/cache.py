# standard imports
import json
import os
from threading import Lock

# lib imports
from six.moves.urllib.parse import quote_plus

# local imports
from common import config
from common import definitions
from common import helpers
from common import logger
from themerr.constants import contributes_to, issue_urls
from themerr import general
from plex.plexapi import get_database_info, setup_plexapi
from themerr import themerr_db
from themerr import tmdb

log = logger.get_logger(name=__name__)

# where the database cache is stored
database_cache_file = os.path.join(definitions.Paths.CONFIG_DIR, 'database_cache.json')
database_cache_lock = Lock()


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
        log.error('Unable to setup plex server, cannot proceed. Ensure Plex is properly configured in the settings.')
        return

    plex_library = plex_server.library

    themerr_db.update_cache()

    sections = plex_library.sections()

    items = dict()

    for section in sections:
        if section.agent not in contributes_to:
            # todo - there is a small chance that a library with an unsupported agent could still have
            # a individual items that was matched with a supported agent...
            continue  # skip unsupported metadata agents

        # get all the items in the section
        media_items = section.all()

        # get all items in the section with theme songs
        media_items_with_themes = section.all(theme__exists=True)

        # get all collections in the section
        collections = section.collections() if config.CONFIG['Themerr']['BOOL_PLEX_COLLECTION_SUPPORT'] else []
        collections_with_themes = section.collections(theme__exists=True) if config.CONFIG['Themerr'][
            'BOOL_PLEX_COLLECTION_SUPPORT'] else []

        # combine the items and collections into one list
        # this is done so that we can process both items and collections in the same loop
        all_items = media_items + collections

        # add each section to the items dict
        items[section.key] = dict(
            key=section.key,
            title=section.title,
            agent=section.agent,
            items=[],
            media_count=len(media_items),
            media_percent_complete=int(
                len(media_items_with_themes) / len(media_items) * 100) if len(media_items_with_themes) else 0,
            collection_count=len(collections),
            collection_percent_complete=int(
                len(collections_with_themes) / len(collections) * 100) if len(collections_with_themes) else 0,
            collections_enabled=config.CONFIG['Themerr']['BOOL_PLEX_COLLECTION_SUPPORT'],
            total_count=len(all_items),
            type=section.type,
        )

        for item in all_items:
            # build the issue url
            database_info = get_database_info(item=item)
            database_type = database_info[0]
            database = database_info[1]
            item_agent = database_info[2]
            database_id = database_info[3]

            og_db = database
            og_db_id = database_id

            year = getattr(item, 'year', None)

            # convert imdb id to tmdb id, so we can build the issue url properly
            if item.type == 'movie' and database_id and (
                    item_agent == 'com.plexapp.agents.imdb'
                    or database_id.startswith('tt')
            ):
                # try to get tmdb id from imdb id
                tmdb_id = tmdb.get_tmdb_id_from_external_id(
                    external_id=database_id, database='imdb', item_type='movie')
                database_id = tmdb_id if tmdb_id else None

            item_issue_url = None

            issue_url = issue_urls.get(database_type)

            if issue_url:
                # override the id since ThemerrDB issues require the slug as part of the url
                if item.type == 'movie':
                    issue_title = f'{getattr(item, "originalTitle", None) or item.title} ({year})'
                elif item.type == 'show':
                    issue_title = f'{item.title} ({year})'
                else:  # collections
                    issue_title = item.title

                if database_id:
                    # url encode the issue title
                    issue_title = quote_plus(issue_title)

                    item_issue_url = issue_url.format(issue_title, database_id)

            if database_type and og_db and og_db_id and themerr_db.item_exists(
                    database_type=database_type,
                    database=og_db,
                    id=og_db_id,
            ):
                issue_action = 'edit'
            else:
                issue_action = 'add'

            if item.theme:
                theme_status = 'complete'
            else:
                if issue_action == 'edit':
                    theme_status = 'failed'
                else:
                    theme_status = 'missing'

            theme_provider = general.get_theme_provider(item=item)

            items[section.key]['items'].append(dict(
                title=item.title,
                agent=item_agent,
                database=database,
                database_type=database_type,
                database_id=database_id,
                issue_action=issue_action,
                issue_url=item_issue_url,
                theme=True if item.theme else False,
                theme_provider=theme_provider,
                theme_status=theme_status,
                type=item.type,
                year=year,
            ))

    with database_cache_lock:
        helpers.file_save(filename=database_cache_file, data=json.dumps(items), binary=False)
