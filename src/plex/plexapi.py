# standard imports
import queue
import os
import time
import threading
from typing import Callable, Optional, Tuple

# lib imports
import requests
from plexapi.alert import AlertListener
from plexapi.base import PlexPartialObject
from plexapi.exceptions import BadRequest
import plexapi.server
from plexapi.utils import reverseSearchType

# local imports
from common import config
from common import helpers
from common import logger
from plex import auth
from themerr.constants import contributes_to, guid_map, media_type_dict
from themerr import general
from themerr import themerr_db
from themerr import tmdb
from youtube.youtube_dl import process_youtube

# fix random _strptime import bug in plexapi
import _strptime  # noqa: F401

log = logger.get_logger(__name__)
PLEX_SETUP_ERROR = 'Unable to setup plex server, cannot proceed. Ensure Plex is properly configured in the settings.'

plex_server = None
alert_listener = None
q = queue.Queue()

# disable auto-reload, because Themerr doesn't rely on it, so it will only slow down the app
# when accessing a missing field
os.environ["PLEXAPI_PLEXAPI_AUTORELOAD"] = "false"


def setup_plexapi() -> Optional[plexapi.server.PlexServer]:
    """
    Create the Plex server object.

    It is required to use PlexAPI in order to add theme music to movies, as the built-in methods for metadata agents
    do not work for movies. This method creates the server object.

    Returns
    -------
    PlexServer
        The PlexServer object.

    Examples
    --------
    >>> setup_plexapi()
    ...
    """
    global plex_server
    plex_token = auth.get_token()
    plex_url = config.CONFIG['Plex']['PLEX_URL']
    if not plex_server:
        if not plex_token:
            log.error('Sign in with Plex in Settings before connecting to the server.')
            return None

        plex_server = connect_plex_server(plex_url=plex_url, plex_token=plex_token)

    return plex_server


def connect_plex_server(plex_url: str, plex_token: str) -> plexapi.server.PlexServer:
    """Connect to a Plex server with a token obtained through Plex sign-in.

    Parameters
    ----------
    plex_url : str
        URL of the selected Plex server.
    plex_token : str
        Plex account token.

    Returns
    -------
    PlexServer
        The connected server.
    """
    sess = requests.Session()
    return plexapi.server.PlexServer(baseurl=plex_url, token=plex_token, session=sess)


def _update_collection_summary(item: PlexPartialObject, data: dict) -> None:
    """Apply a collection summary when it is available and editable.

    Parameters
    ----------
    item : PlexPartialObject
        Collection to update.
    data : dict
        ThemerrDB metadata.
    """
    if item.isLocked(field='summary') and not config.CONFIG['Themerr']['BOOL_IGNORE_LOCKED_FIELDS']:
        log.debug(f'Not overwriting locked summary for collection: {item.title}')
        return
    if 'overview' not in data or item.summary == data['overview']:
        return
    log.info(f'Updating summary for collection: {item.title}')
    try:
        item.editSummary(summary=data['overview'], locked=False)
    except Exception:
        log.exception(f'{item.ratingKey}: Error updating summary')


def _update_collection_metadata(item: PlexPartialObject, agent: str, data: dict) -> None:
    """Update supported collection artwork and summary.

    Parameters
    ----------
    item : PlexPartialObject
        Collection to update.
    agent : str
        Metadata agent identifier.
    data : dict
        ThemerrDB metadata.
    """
    if item.type != 'collection' or agent != 'tv.plex.agents.movie' or not config.CONFIG['Themerr'][
            'BOOL_UPDATE_COLLECTION_METADATA']:
        return

    for field, media_type in (('poster_path', 'posters'), ('backdrop_path', 'art')):
        if field in data:
            media_path = data[field]
            add_media(item=item, media_type=media_type, media_url_id=media_path,
                      media_url=f'https://image.tmdb.org/t/p/original{media_path}')
    _update_collection_summary(item, data)


def _update_theme(item: PlexPartialObject, data: dict) -> None:
    """Update an item theme when Plex and Themerr settings permit it.

    Parameters
    ----------
    item : PlexPartialObject
        Plex item to update.
    data : dict
        ThemerrDB metadata.
    """
    if item.isLocked(field='theme') and not config.CONFIG['Themerr']['BOOL_IGNORE_LOCKED_FIELDS']:
        log.debug(f'Not overwriting locked theme for {item.type}: {item.title}')
        return
    if (not config.CONFIG['Themerr']['BOOL_OVERWRITE_PLEX_PROVIDED_THEMES'] and
            general.get_theme_provider(item=item) == 'plex'):
        log.debug(f'Not overwriting Plex provided theme for {item.type}: {item.title}')
        return
    if 'youtube_theme_url' not in data:
        log.info(f'{item.ratingKey}: No theme song found for {item.title} ({item.year})')
        return

    yt_video_url = data['youtube_theme_url']
    settings_hash = general.get_themerr_settings_hash()
    themerr_data = general.get_themerr_json_data(item=item)
    try:
        skip = (themerr_data['settings_hash'] == settings_hash and
                themerr_data[media_type_dict['themes']['themerr_data_key']] == yt_video_url)
    except KeyError:
        skip = False
    if skip:
        log.info(f'Skipping {media_type_dict["themes"]["name"]} for '
                 f'type: {item.type}, title: {item.title}, rating_key: {item.ratingKey}')
        return

    try:
        theme_url = process_youtube(url=yt_video_url)
    except Exception:
        log.exception(f'{item.ratingKey}: Error processing youtube url')
        return
    if theme_url:
        add_media(item=item, media_type='themes', media_url_id=yt_video_url, media_url=theme_url)


def update_plex_item(rating_key: int) -> bool:
    """
    Automated update of Plex item using only the rating key.

    Given the rating key, this function will automatically handle collecting the required information to update the
    theme song, and any other metadata.

    Parameters
    ----------
    rating_key : int
        The rating key of the item to be updated.

    Returns
    -------
    py:class:`bool`
        True if the item was updated successfully, False otherwise.

    Examples
    --------
    >>> update_plex_item(rating_key=12345)
    """
    item = get_plex_item(rating_key=rating_key)
    if not item:
        log.error(f'Could not find item with rating key: {rating_key}')
        return False

    database_type, database, agent, database_id = get_database_info(item=item)
    log.debug('-' * 50)
    log.debug(f'item title: {item.title}')
    log.debug(f'item type: {item.type}')
    log.debug(f'database_info: {(database_type, database, agent, database_id)}')

    if not (database and database_type and database_id):
        return False
    if not themerr_db.item_exists(database_type=database_type, database=database, id=database_id):
        log.debug(f'{item.type} item does not exist in ThemerrDB, skipping: {item.title} ({database_id})')
        return False

    try:
        data = helpers.json_get(
            cache_time=3600,
            url=f'https://app.lizardbyte.dev/ThemerrDB/{database_type}/{database}/{database_id}.json',
        )
    except Exception:
        log.exception(f'{item.ratingKey}: Error retrieving data from ThemerrDB')
        return False
    if not data:
        return False

    log.debug(f'data found for {item.type} {item.title}')
    _update_collection_metadata(item, agent, data)
    _update_theme(item, data)
    return True


def add_media(
        item: PlexPartialObject,
        media_type: str,
        media_url_id: str,
        media_file: Optional[str] = None,
        media_url: Optional[str] = None,
) -> bool:
    """
    Apply media to the specified item.

    Adds theme song to the item specified by the ``rating_key``. If the same theme song is already present, it will be
    skipped.

    Parameters
    ----------
    item : PlexPartialObject
        The Plex item to add the theme to.
    media_type : str
        The type of media to add. Must be one of 'art', 'posters', or 'themes'.
    media_url_id : str
        The url or id of the media.
    media_file : Optional[str]
        Full path to media file.
    media_url : Optional[str]
        URL of media.

    Returns
    -------
    py:class:`bool`
        True if the media was added successfully or already present, False otherwise.

    Examples
    --------
    >>> add_media(item=..., media_type='themes', media_url_id=..., media_url=...)
    >>> add_media(item=..., media_type='themes', media_url_url=..., media_file=...)
    """
    uploaded = False

    settings_hash = general.get_themerr_settings_hash()
    themerr_data = general.get_themerr_json_data(item=item)

    if (item.isLocked(field=media_type_dict[media_type]['plex_field']) and
            not config.CONFIG['Themerr']['BOOL_IGNORE_LOCKED_FIELDS']):
        log.info(f'Not overwriting locked "{media_type_dict[media_type]['name']}" for {item.type}: {item.title}')
        return False

    if not (media_file or media_url):
        log.warning(f'No theme songs provided for type: {item.type}, title: {item.title}, rating_key: {item.ratingKey}')
        return False

    log.info(f'Plexapi attempting to upload {media_type_dict[media_type]['name']} for '
             f'type: {item.type}, title: {item.title}, rating_key: {item.ratingKey}')

    if (themerr_data.get('settings_hash') == settings_hash and
            themerr_data.get(media_type_dict[media_type]['themerr_data_key']) == media_url_id):
        log.info(f'Skipping {media_type_dict[media_type]['name']} for '
                 f'type: {item.type}, title: {item.title}, rating_key: {item.ratingKey}')
        return False

    if config.CONFIG['Themerr'][media_type_dict[media_type]['remove_pref']]:
        general.remove_uploaded_media(item=item, media_type=media_type)

    log.info(f'Attempting to upload {media_type_dict[media_type]['name']} for '
             f'type: {item.type}, title: {item.title}, rating_key: {item.ratingKey}')
    if media_file:
        uploaded = upload_media(item=item, method=media_type_dict[media_type]['method'](item), filepath=media_file)
    if media_url:
        uploaded = upload_media(item=item, method=media_type_dict[media_type]['method'](item), url=media_url)

    if uploaded:
        # new data for themerr.json
        new_themerr_data = {
            'settings_hash': settings_hash
        }
        new_themerr_data[media_type_dict[media_type]['themerr_data_key']] = media_url_id

        general.update_themerr_data_file(item=item, new_themerr_data=new_themerr_data)

        # unlock the field since it contains an automatically added value
        change_lock_status(item=item, field=media_type_dict[media_type]['plex_field'], lock=False)
    else:
        log.debug(f'Could not upload {media_type_dict[media_type]['name']} for '
                  f'type: {item.type}, title: {item.title}, rating_key: {item.ratingKey}')

    return uploaded


def change_lock_status(item: PlexPartialObject, field: str, lock: bool = False) -> bool:
    """
    Change the lock status of the specified field.

    Parameters
    ----------
    item : PlexPartialObject
        The Plex item to unlock the field for.
    field : str
        The field to unlock.
    lock : py:class:`bool`
        True to lock the field, False to unlock the field.

    Returns
    -------
    py:class:`bool`
        True if the lock status matches the requested lock status, False otherwise.

    Examples
    --------
    >>> change_lock_status(item=..., field='theme', lock=False)
    """
    lock_string = 'lock' if lock else 'unlock'

    current_status = item.isLocked(field=field)
    if current_status == lock:
        log.debug(f'Lock field "{field}" is already {lock} for item: {item.title}')
        return current_status == lock

    edits = {
        f'{field}.locked': int(lock),
    }

    count = 0
    successful = False
    exception = None
    while count < 3:  # there are random read timeouts
        try:
            item.edit(**edits)
        except requests.ReadTimeout as e:
            exception = e
            time.sleep(5)
            count += 1
        else:
            successful = True
            break

    if not successful:
        log.error(f'{item.ratingKey}: Error {lock_string}ing field: {exception}')

    # we need to reload the item to get the new lock status
    reload_kwargs = {field: True}
    item.reload(**reload_kwargs)

    locked = item.isLocked(field=field)
    if locked != lock:
        log.error(f'{item.ratingKey}: Error {lock_string}ing field: {locked} != {lock}')

    return locked == lock


def upload_media(
        item: PlexPartialObject,
        method: Callable,
        filepath: Optional[str] = None,
        url: Optional[str] = None,
) -> bool:
    """
    Upload media to the specified item.

    Uploads art, poster, or theme to the item specified by the ``item``.

    Parameters
    ----------
    item : PlexPartialObject
        The Plex item to upload the theme to.
    method : Callable
        The method to use to upload the theme.
    filepath : Optional[str]
        The path to the theme song.
    url : Optional[str]
        The url to the theme song.

    Returns
    -------
    py:class:`bool`
        True if the theme was uploaded successfully, False otherwise.

    Examples
    --------
    >>> upload_media(item=..., method=item.uploadArt, url=...)
    >>> upload_media(item=..., method=item.uploadPoster, url=...)
    >>> upload_media(item=..., method=item.uploadTheme, url=...)
    ...
    """
    count = 0
    while count <= int(config.CONFIG['Themerr']['INT_PLEXAPI_UPLOAD_RETRIES_MAX']):
        try:
            if filepath or url:
                source = {'filepath': filepath} if filepath else {'url': url}
                if method == item.uploadTheme:
                    source['timeout'] = int(config.CONFIG['Themerr']['INT_PLEXAPI_PLEXAPI_TIMEOUT'])
                method(**source)
        except BadRequest as e:
            sleep_time = 2 ** count
            log.error(f'{item.ratingKey}: Error uploading media: {e}')
            log.error(f'{item.ratingKey}: Trying again in : {sleep_time} seconds')
            time.sleep(sleep_time)
            count += 1
        else:
            return True
    return False


def _movie_database_info(item: PlexPartialObject) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Resolve a movie's preferred external database identifier.

    Parameters
    ----------
    item : PlexPartialObject
        Plex movie.

    Returns
    -------
    tuple
        Database type, database, agent, and identifier.
    """
    if not item.guids:
        return None, None, None, None

    database = None
    database_id = None
    for guid in item.guids:
        split_guid = guid.id.split('://')
        candidate = guid_map[split_guid[0]]
        if candidate == 'imdb':
            database, database_id = candidate, split_guid[1]
        if candidate == 'themoviedb':
            database, database_id = candidate, split_guid[1]
            break
    return 'movies', database, 'tv.plex.agents.movie', database_id


def _show_database_info(item: PlexPartialObject) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Resolve a show's preferred external database identifier.

    Parameters
    ----------
    item : PlexPartialObject
        Plex show.

    Returns
    -------
    tuple
        Database type, database, agent, and identifier.
    """
    if not item.guids:
        return 'tv_shows', None, None, None

    external_guid = None
    for guid in item.guids:
        split_guid = guid.id.split('://')
        candidate = guid_map.get(split_guid[0])
        if candidate == 'themoviedb':
            return 'tv_shows', candidate, 'tv.plex.agents.series', split_guid[1]
        if candidate in ('imdb', 'thetvdb'):
            external_guid = split_guid

    if external_guid:
        database_id = tmdb.get_tmdb_id_from_external_id(
            external_id=external_guid[1], database=external_guid[0], item_type='tv', title=item.title,
        )
        if database_id:
            return 'tv_shows', 'themoviedb', 'tv.plex.agents.series', database_id
    return 'tv_shows', None, 'tv.plex.agents.series', None


def _collection_database_info(item: PlexPartialObject, plex) -> Tuple[str, str, str, Optional[str]]:
    """Resolve a collection using its library agent and title.

    Parameters
    ----------
    item : PlexPartialObject
        Plex collection.
    plex : PlexServer
        Connected Plex server.

    Returns
    -------
    tuple
        Database type, database, agent, and identifier.
    """
    section = plex.library.sectionByID(item.librarySectionID)
    database_id = tmdb.get_tmdb_id_from_collection(search_query=item.title, language=section.language)
    return 'movie_collections', 'themoviedb', section.agent, database_id


def get_database_info(item: PlexPartialObject) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Get the database info for the specified item.

    Get the ``database_type``, ``database``, ``agent``, ``database_id`` which can be used to locate the theme song
    in ThemerrDB.

    Parameters
    ----------
    item : PlexPartialObject
        The Plex item to get the database info for.

    Returns
    -------
    Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]
        The ``database_type``, ``database``, ``agent``, ``database_id``.

    Examples
    --------
    >>> get_database_info(item=...)
    """
    log.debug(f'Getting database info for item: {item.title}')

    plex = setup_plexapi()
    if not plex:
        log.error(PLEX_SETUP_ERROR)
        return None, None, None, None

    if item.type == 'movie':
        database_info = _movie_database_info(item)
    elif item.type == 'show':
        database_info = _show_database_info(item)
    elif item.type == 'collection':
        database_info = _collection_database_info(item, plex)
    else:
        database_info = None, None, None, None

    log.debug(f'Database info for item: {item.title}, database_info: {database_info}')
    return database_info


def get_plex_item(rating_key: int) -> Optional[PlexPartialObject]:
    """
    Get any item from the Plex Server.

    This function is used to get an item from the Plex Server. It can then be used to get the metadata for the item.

    Parameters
    ----------
    rating_key : int
        The ``rating_key`` of the item to get.

    Returns
    -------
    PlexPartialObject
        The Plex item from the Plex Server.

    Examples
    --------
    >>> get_plex_item(rating_key=1)
    ...
    """
    plex = setup_plexapi()
    if not plex:
        log.error(PLEX_SETUP_ERROR)
        return None
    item = plex.fetchItem(ekey=rating_key)

    return item


def process_queue() -> None:
    """
    Add items to the queue.

    This is an endless loop to add items to the queue.

    Examples
    --------
    >>> process_queue()
    ...
    """
    while True:
        rating_key = q.get()  # get the rating_key from the queue
        try:
            update_plex_item(rating_key=rating_key)  # process that rating_key
        except Exception as e:
            log.exception(f'Unexpected error processing rating key: {rating_key}, error: {e}')
        q.task_done()  # tells the queue that we are done with this item


def start_queue_threads() -> None:
    """
    Start queue threads.

    Start the queue threads based on the number of threads set in the preferences.

    Examples
    --------
    >>> start_queue_threads()
    ...
    """
    # create multiple threads for processing themes faster
    # minimum value of 1
    for t in range(max(1, int(config.CONFIG['Themerr']['INT_PLEXAPI_UPLOAD_THREADS']))):
        try:
            # for each thread, start it
            t = threading.Thread(target=process_queue)
            # when we set daemon to true, that thread will end when the main thread ends
            t.daemon = True
            # start the daemon thread
            t.start()
        except RuntimeError as e:
            log.error(f'RuntimeError encountered: {e}')
            break


def plex_listener() -> None:
    """
    Listen for events from Plex server.

    Send events to ``plex_listener_handler`` and errors to ``Log.Error``.

    Examples
    --------
    >>> plex_listener()
    ...
    """
    global alert_listener
    stop_plex_listener()
    plex = setup_plexapi()
    if not plex:
        log.error(PLEX_SETUP_ERROR)
        return
    alert_listener = AlertListener(server=plex, callback=plex_listener_handler, callbackError=log.error)
    alert_listener.start()


def stop_plex_listener() -> None:
    """Stop the active Plex event listener, if one exists."""
    global alert_listener
    if alert_listener is not None:
        if getattr(alert_listener, '_ws', None) is not None:
            alert_listener.stop()
        alert_listener = None


def plex_listener_handler(data: dict) -> None:
    """
    Process events from ``plex_listener()``.

    Check if we need to add an item to the queue. This is used to automatically add themes to items from the
    new Plex Movie agent, since metadata agents cannot extend it.

    Parameters
    ----------
    data : dict
        Data received from the Plex server.

    Examples
    --------
    >>> plex_listener_handler(data={'type': 'timeline'})
    ...
    """
    if data['type'] != 'timeline':
        return

    for entry in data['TimelineEntry']:
        if entry['state'] != 5 or entry['identifier'] != 'com.plexapp.plugins.library':
            continue

        media_type = reverseSearchType(libtype=entry['type'])
        supported = (
            (media_type == 'movie' and config.CONFIG['Themerr']['BOOL_PLEX_MOVIE_SUPPORT']) or
            (media_type == 'show' and config.CONFIG['Themerr']['BOOL_PLEX_SERIES_SUPPORT'])
        )
        if not supported:
            continue

        rating_key = int(entry['itemID'])
        # Repeated timeline events should queue an item only once.
        if rating_key not in q.queue:
            q.put(item=rating_key)


def _items_for_section(section) -> list:
    """Collect supported media and collections from one Plex section.

    Parameters
    ----------
    section : LibrarySection
        Section being scanned.

    Returns
    -------
    list
        Items eligible for the scheduled update.
    """
    if section.type == 'movie':
        media_items = section.all() if config.CONFIG['Themerr']['BOOL_PLEX_MOVIE_SUPPORT'] else []
        collections = section.collections() if config.CONFIG['Themerr']['BOOL_PLEX_COLLECTION_SUPPORT'] else []
        return media_items + collections
    if section.type == 'show' and config.CONFIG['Themerr']['BOOL_PLEX_SERIES_SUPPORT']:
        return section.all()
    return []


def scheduled_update() -> None:
    """
    Update all items in the Plex Server.

    This is used to update all items in the Plex Server. It is called from a scheduled task.

    Examples
    --------
    >>> scheduled_update()

    See Also
    --------
    scheduled_tasks.setup_scheduling : The method where the scheduled task is configurerd.
    scheduled_tasks.schedule_loop : The method that runs the pending scheduled tasks.
    """
    plex = setup_plexapi()
    if not plex:
        log.error(PLEX_SETUP_ERROR)
        return

    themerr_db.update_cache()

    plex_library = plex.library

    sections = plex_library.sections()
    ignored_library_ids = {
        library_id.strip()
        for library_id in config.CONFIG['Themerr']['IGNORED_LIBRARY_IDS'].split(',')
        if library_id.strip()
    }

    for section in sections:
        if str(section.key) in ignored_library_ids:
            log.debug(f'Skipping ignored Plex library: {section.title}')
            continue
        if section.agent not in contributes_to:
            # with legacy agents, not all items in the library had to match to the library agent
            # not the case with new agents (probably)
            continue  # skip unsupported metadata agents

        # check if the agent is enabled
        if not general.continue_update(item_agent=section.agent):
            log.debug(f'Themerr-plex is disabled for agent "{section.agent}"')
            continue

        for item in _items_for_section(section):
            if item.ratingKey not in q.queue:
                q.put(item=item.ratingKey)
