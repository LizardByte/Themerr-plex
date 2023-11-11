# -*- coding: utf-8 -*-

# standard imports
import os
import time
import threading

# plex debugging
try:
    import plexhints  # noqa: F401
except ImportError:
    pass
else:  # the code is running outside of Plex
    from plexhints.log_kit import Log  # log kit
    from plexhints.parse_kit import JSON, XML  # parse kit
    from plexhints.prefs_kit import Prefs  # prefs kit

# imports from Libraries\Shared
from future.moves import queue
import requests
from typing import Callable, Optional, Tuple
import urllib3
from urllib3.exceptions import InsecureRequestWarning
from plexapi.alert import AlertListener
from plexapi.base import PlexPartialObject
from plexapi.exceptions import BadRequest
import plexapi.server
from plexapi.utils import reverseSearchType

# local imports
from constants import contributes_to, guid_map, media_type_dict
import general_helper
import lizardbyte_db_helper
import themerr_db_helper
import tmdb_helper
from youtube_dl_helper import process_youtube

plex = None

q = queue.Queue()

# disable auto-reload, because Themerr doesn't rely on it, so it will only slow down the app
# when accessing a missing field
os.environ["PLEXAPI_PLEXAPI_AUTORELOAD"] = "false"

# the explicit IPv4 address is used because `localhost` can resolve to ::1, which `websocket` rejects
plex_url = 'http://127.0.0.1:32400'
plex_token = os.environ.get('PLEXTOKEN')

plex_section_type_settings_map = dict(
    album=9,
    artist=8,
    movie=1,
    photo=13,
    show=2,
)


def setup_plexapi():
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
    global plex
    if not plex:
        if not plex_token:
            Log.Error('Plex token not found in environment, cannot proceed.')
            return False

        sess = requests.Session()
        sess.verify = False  # Ignore verifying the SSL certificate
        urllib3.disable_warnings(InsecureRequestWarning)  # Disable the insecure request warning

        # create the plex server object
        plex = plexapi.server.PlexServer(baseurl=plex_url, token=plex_token, session=sess)

    return plex


def is_field_locked(item, field_name):
    # type: (any, str) -> bool
    """
    Check if the specified field is locked.
    
    This is used to ensure a field has not been manually set by the user.

    Parameters
    ----------
    item : any
        The Plex item to check.
    field_name : str
        The name of the field to check.

    Returns
    -------
    bool
        True if the field is locked, False otherwise.

    Examples
    --------
    >>> is_field_locked(item=..., field_name='theme')
    False
    """
    for field in item.fields:
        if field.name == field_name:
            return field.locked
    return False


def update_plex_item(rating_key):
    # type: (int) -> bool
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
    bool
        True if the item was updated successfully, False otherwise.

    Examples
    --------
    >>> update_plex_item(rating_key=12345)
    """
    # first get the plex item
    item = get_plex_item(rating_key=rating_key)

    if not item:
        Log.Error('Could not find item with rating key: %s' % rating_key)
        return False

    database_info = get_database_info(item=item)
    Log.Debug('-' * 50)
    Log.Debug('item title: {}'.format(item.title))
    Log.Debug('item type: {}'.format(item.type))
    Log.Debug('database_info: {}'.format(database_info))

    database_type = database_info[0]
    database = database_info[1]
    agent = database_info[2]
    database_id = database_info[3]

    if database and database_type and database_id:
        if not themerr_db_helper.item_exists(database_type=database_type, database=database, id=database_id):
            Log.Debug('{} item does not exist in ThemerrDB, skipping: {} ({})'
                      .format(item.type, item.title, database_id))
            return False

        try:
            data = JSON.ObjectFromURL(
                cacheTime=3600,
                url='https://app.lizardbyte.dev/ThemerrDB/{}/{}/{}.json'.format(database_type, database, database_id),
                errors='ignore'  # don't crash the plugin
            )
        except Exception as e:
            Log.Error('{}: Error retrieving data from ThemerrDB: {}'.format(item.ratingKey, e))
        else:
            if data:
                # update collection metadata
                Log.Debug('data found for {} {}'.format(item.type, item.title))
                if item.type == 'collection':
                    # determine if we want to update the metadata based on the agent and user preferences
                    update_collection_metadata = False

                    if agent == 'tv.plex.agents.movie':  # new Plex Movie agent
                        if Prefs['bool_update_collection_metadata_plex_movie']:
                            update_collection_metadata = True
                    elif database != 'igdb':  # any other legacy agents except RetroArcher
                        # game collections/franchises don't have extended metadata
                        if Prefs['bool_update_collection_metadata_legacy']:
                            update_collection_metadata = True

                    if update_collection_metadata:
                        # update poster
                        try:
                            url = 'https://image.tmdb.org/t/p/original{}'.format(data['poster_path'])
                        except KeyError:
                            pass
                        else:
                            add_media(item=item, media_type='posters', media_url_id=data['poster_path'], media_url=url)
                        # update art
                        try:
                            url = 'https://image.tmdb.org/t/p/original{}'.format(data['backdrop_path'])
                        except KeyError:
                            pass
                        else:
                            add_media(item=item, media_type='art', media_url_id=data['backdrop_path'], media_url=url)
                        # update summary
                        if is_field_locked(item=item, field_name="summary"):
                            Log.Debug('Not overwriting locked summary for collection: {}'.format(item.title))
                        else:
                            try:
                                summary = data['overview']
                            except KeyError:
                                pass
                            else:
                                if item.summary != summary:
                                    Log.Info('Updating summary for collection: {}'.format(item.title))
                                    try:
                                        item.editSummary(summary=summary, locked=False)
                                    except Exception as e:
                                        Log.Error('{}: Error updating summary: {}'.format(item.ratingKey, e))

                if is_field_locked(item=item, field_name="theme"):
                    Log.Debug('Not overwriting locked theme for {}: {}'.format(item.type, item.title))
                else:
                    # get youtube_url
                    try:
                        yt_video_url = data['youtube_theme_url']
                    except KeyError:
                        Log.Info('{}: No theme song found for {} ({})'.format(item.ratingKey, item.title, item.year))
                    else:
                        settings_hash = general_helper.get_themerr_settings_hash()
                        themerr_data = general_helper.get_themerr_json_data(item=item)

                        try:
                            skip = themerr_data['settings_hash'] == settings_hash \
                                and themerr_data[media_type_dict['themes']['themerr_data_key']] == yt_video_url
                        except KeyError:
                            skip = False

                        if skip:
                            Log.Info('Skipping {} for type: {}, title: {}, rating_key: {}'.format(
                                media_type_dict['themes']['name'], item.type, item.title, item.ratingKey
                            ))
                        else:
                            try:
                                theme_url = process_youtube(url=yt_video_url)
                            except Exception as e:
                                Log.Exception('{}: Error processing youtube url: {}'.format(item.ratingKey, e))
                            else:
                                if theme_url:
                                    add_media(item=item, media_type='themes',
                                              media_url_id=yt_video_url, media_url=theme_url)


def add_media(item, media_type, media_url_id, media_file=None, media_url=None):
    # type: (PlexPartialObject, str, str, Optional[str], Optional[str]) -> bool
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
    bool
        True if the media was added successfully or already present, False otherwise.

    Examples
    --------
    >>> add_media(item=..., media_type='themes', media_url_id=..., media_url=...)
    >>> add_media(item=..., media_type='themes', media_url_url=..., media_file=...)
    """
    uploaded = False

    settings_hash = general_helper.get_themerr_settings_hash()
    themerr_data = general_helper.get_themerr_json_data(item=item)

    if is_field_locked(item=item, field_name=media_type_dict[media_type]['plex_field']):
        Log.Info('Not overwriting locked "{}" for {}: {}'.format(
            media_type_dict[media_type]['name'], item.type, item.title
        ))
        return False

    if media_file or media_url:
        global plex
        if not plex:
            plex = setup_plexapi()

        Log.Info('Plexapi attempting to upload {} for type: {}, title: {}, rating_key: {}'.format(
            media_type_dict[media_type]['name'], item.type, item.title, item.ratingKey
        ))

        try:
            if themerr_data['settings_hash'] == settings_hash \
                    and themerr_data[media_type_dict[media_type]['themerr_data_key']] == media_url_id:
                Log.Info('Skipping {} for type: {}, title: {}, rating_key: {}'.format(
                    media_type_dict[media_type]['name'], item.type, item.title, item.ratingKey
                ))

                # false because we aren't doing anything, and the listener will not see this item again
                return False
        except KeyError:
            pass

        # remove existing theme uploads
        if Prefs[media_type_dict[media_type]['remove_pref']]:
            general_helper.remove_uploaded_media(item=item, media_type=media_type)

        Log.Info('Attempting to upload {} for type: {}, title: {}, rating_key: {}'.format(
            media_type_dict[media_type]['name'], item.type, item.title, item.ratingKey
        ))
        if media_file:
            uploaded = upload_media(item=item, method=media_type_dict[media_type]['method'](item), filepath=media_file)
        if media_url:
            uploaded = upload_media(item=item, method=media_type_dict[media_type]['method'](item), url=media_url)
    else:
        Log.Warning('No theme songs provided for type: {}, title: {}, rating_key: {}'.format(
            item.type, item.title, item.ratingKey
        ))

    if uploaded:
        # new data for themerr.json
        new_themerr_data = dict(
            settings_hash=settings_hash
        )
        new_themerr_data[media_type_dict[media_type]['themerr_data_key']] = media_url_id

        general_helper.update_themerr_data_file(item=item, new_themerr_data=new_themerr_data)

        # unlock the field since it contains an automatically added value
        getattr(item, "_edit")(**{'{}.locked'.format(media_type_dict[media_type]['plex_field']): 0})
    else:
        Log.Debug('Could not upload {} for type: {}, title: {}, rating_key: {}'.format(
            media_type_dict[media_type]['name'], item.type, item.title, item.ratingKey
        ))

    return uploaded


def upload_media(item, method, filepath=None, url=None):
    # type: (PlexPartialObject, Callable, Optional[str], Optional[str]) -> bool
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
    bool
        True if the theme was uploaded successfully, False otherwise.

    Examples
    --------
    >>> upload_media(item=..., method=item.uploadArt, url=...)
    >>> upload_media(item=..., method=item.uploadPoster, url=...)
    >>> upload_media(item=..., method=item.uploadTheme, url=...)
    ...
    """
    count = 0
    while count <= int(Prefs['int_plexapi_upload_retries_max']):
        try:
            if filepath:
                if method == item.uploadTheme:
                    method(filepath=filepath, timeout=int(Prefs['int_plexapi_plexapi_timeout']))
                else:
                    method(filepath=filepath)
            elif url:
                if method == item.uploadTheme:
                    method(url=url, timeout=int(Prefs['int_plexapi_plexapi_timeout']))
                else:
                    method(url=url)
        except BadRequest as e:
            sleep_time = 2**count
            Log.Error('%s: Error uploading media: %s' % (item.ratingKey, e))
            Log.Error('%s: Trying again in : %s' % (item.ratingKey, sleep_time))
            time.sleep(sleep_time)
            count += 1
        else:
            return True
    return False


def get_database_info(item):
    # type: (PlexPartialObject) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]
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
    Log.Debug('Getting database info for item: %s' % item.title)

    # setup plex just in case
    global plex
    if not plex:
        plex = setup_plexapi()

    agent = None
    database = None
    database_id = None
    database_type = None

    if item.type == 'movie':
        if item.guids:  # guids is a blank list for items from legacy agents, only available for new agent items
            agent = 'tv.plex.agents.movie'
            database_type = 'movies'
            for guid in item.guids:
                split_guid = guid.id.split('://')
                temp_database = guid_map[split_guid[0]]
                temp_database_id = split_guid[1]

                if temp_database == 'imdb':
                    database_id = temp_database_id
                    database = temp_database

                if temp_database == 'themoviedb':  # tmdb is our prefered db, so we break if found
                    database_id = temp_database_id
                    database = temp_database
                    break
        elif item.guid:
            split_guid = item.guid.split('://')
            agent = split_guid[0]
            if agent == 'dev.lizardbyte.retroarcher-plex':
                # dev.lizardbyte.retroarcher-plex://{igdb-1638}{platform-4}{(USA)}?lang=en
                database_type = 'games'
                database = 'igdb'
                database_id = item.guid.split('igdb-')[1].split('}')[0]
            elif agent == 'com.plexapp.agents.themoviedb':
                # com.plexapp.agents.themoviedb://363088?lang=en
                database_type = 'movies'
                database = 'themoviedb'
                database_id = item.guid.split('://')[1].split('?')[0]
            elif agent == 'com.plexapp.agents.imdb':
                # com.plexapp.agents.imdb://tt0113189?lang=en
                database_type = 'movies'
                database = 'imdb'
                database_id = item.guid.split('://')[1].split('?')[0]

    elif item.type == 'collection':
        # this is tricky since collections don't match up with any of the databases
        # we'll use the collection title and try to find a match

        # using the section id, we can probably figure out the agent
        section = plex.library.sectionByID(item.librarySectionID)
        agent = section.agent

        if agent == 'dev.lizardbyte.retroarcher-plex':
            # this collection is for a game library
            database = 'igdb'
            collection_data = lizardbyte_db_helper.get_igdb_id_from_collection(search_query=item.title)
            if collection_data:
                database_id = collection_data[0]
                database_type = collection_data[1]
        else:
            database = 'themoviedb'
            database_type = 'movie_collections'
            database_id = tmdb_helper.get_tmdb_id_from_collection(search_query=item.title)

    Log.Debug('Database info for item: {}, database_info: {}'.format(
        item.title, (database_type, database, agent, database_id)))
    return database_type, database, agent, database_id


def get_plex_item(rating_key):
    # type: (int) -> PlexPartialObject
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
    global plex
    if not plex:
        plex = setup_plexapi()
    if plex:
        item = plex.fetchItem(ekey=rating_key)
    else:
        item = None

    return item


def process_queue():
    # type: () -> None
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
            Log.Exception('Unexpected error processing rating key: %s, error: %s' % (rating_key, e))
        q.task_done()  # tells the queue that we are done with this item


def start_queue_threads():
    # type: () -> None
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
    for t in range(max(1, int(Prefs['int_plexapi_upload_threads']))):
        try:
            # for each thread, start it
            t = threading.Thread(target=process_queue)
            # when we set daemon to true, that thread will end when the main thread ends
            t.daemon = True
            # start the daemon thread
            t.start()
        except RuntimeError as e:
            Log.Error('RuntimeError encountered: %s' % e)
            break


def plex_listener():
    # type: () -> None
    """
    Listen for events from Plex server.

    Send events to ``plex_listener_handler`` and errors to ``Log.Error``.

    Examples
    --------
    >>> plex_listener()
    ...
    """
    global plex
    if not plex:
        plex = setup_plexapi()
    listener = AlertListener(server=plex, callback=plex_listener_handler, callbackError=Log.Error)
    listener.start()


def plex_listener_handler(data):
    # type: (dict) -> None
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
    # Log.Debug(data)
    if data['type'] == 'timeline':
        for entry in data['TimelineEntry']:
            # known state values:
            # https://python-plexapi.readthedocs.io/en/latest/modules/alert.html#module-plexapi.alert

            # known search types:
            # https://github.com/pkkid/python-plexapi/blob/8b3235445f6b3051c39ff6d6fc5d49f4e674d576/plexapi/utils.py#L35-L55
            if (reverseSearchType(libtype=entry['type']) == 'movie'
                    and entry['state'] == 5
                    and entry['identifier'] == 'com.plexapp.plugins.library'):
                # identifier always appears to be `com.plexapp.plugins.library` for updating library metadata
                # entry['title'] = movie title
                # entry['itemID'] = rating key

                rating_key = int(entry['itemID'])

                # since we added the themerr json file, we no longer need to keep track of whether the update
                # here is from Themerr updating the theme, as we will just skip it if no changes are required
                if rating_key not in q.queue:  # if the item was not in the list, then add it to the queue
                    q.put(item=rating_key)


def scheduled_update():
    # type: () -> None
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
    global plex
    if not plex:
        plex = setup_plexapi()

    themerr_db_helper.update_cache()

    plex_library = plex.library

    sections = plex_library.sections()

    for section in sections:
        if section.agent not in contributes_to:
            # todo - there is a small chance that a library with an unsupported agent could still have
            # individual items that was matched with a supported agent...
            continue  # skip unsupported metadata agents

        if section.agent == 'tv.plex.agents.movie':
            if not Prefs['bool_plex_movie_support']:
                continue
        elif section.agent in contributes_to:
            # check if the agent is enabled
            if not plex_token:
                Log.Error('Plex token not found in environment, cannot proceed.')
                continue

            # get the settings for this agent
            settings_url = '{}/system/agents/{}/config/{}'.format(
                plex_url, section.agent, plex_section_type_settings_map[section.type])
            settings_data = XML.ElementFromURL(
                url=settings_url,
                cacheTime=0
            )
            Log.Debug('settings data: {}'.format(settings_data))

            themerr_plex_element = settings_data.find(".//Agent[@name='Themerr-plex']")
            if themerr_plex_element.get('enabled') != '1':  # Plex is using a string
                Log.Debug('Themerr-plex is disabled for agent "{}"'.format(section.agent))
                continue

        # get all the items in the section
        media_items = section.all() if Prefs['bool_auto_update_movie_themes'] else []

        # get all collections in the section
        collections = section.collections() if Prefs['bool_auto_update_collection_themes'] else []

        # combine the items and collections into one list
        # this is done so that we can process both items and collections in the same loop
        all_items = media_items + collections

        for item in all_items:
            if item.ratingKey not in q.queue:
                q.put(item=item.ratingKey)
