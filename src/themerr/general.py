# standard imports
import hashlib
import json
import os
import shutil
from typing import Optional

# lib imports
from plexapi.base import PlexPartialObject

# local imports
from common import config
from common import definitions
from common import helpers
from common import logger
from themerr.constants import metadata_type_map

log = logger.get_logger(__name__)

# constants
legacy_keys = [
    'downloaded_timestamp'
]


def _get_metadata_path(item: PlexPartialObject) -> str:
    """
    Get the metadata path of the item.

    Get the hashed path of the metadata directory for the item specified by the ``item``.

    Parameters
    ----------
    item : PlexPartialObject
        The item to get the theme upload path for.

    Returns
    -------
    str
        The path to the metadata directory.

    Examples
    --------
    >>> _get_metadata_path(item=...)
    "...bundle"
    """
    guid = item.guid
    full_hash = hashlib.sha1(guid).hexdigest()
    metadata_path = os.path.join(
        config.CONFIG['Plex']['PLEX_APP_SUPPORT_PATH'], 'Metadata', metadata_type_map[item.type],
        full_hash[0], full_hash[1:] + '.bundle')
    return metadata_path


def continue_update(item_agent: str) -> bool:
    """
    Check if the specified agent should continue updating.

    Parameters
    ----------
    item_agent : str
        The agent to check.

    Returns
    -------
    py:class:`bool`
        True if the agent should continue updating, False otherwise.

    Examples
    --------
    >>> continue_update(item_agent='tv.plex.agents.movie')
    True
    >>> continue_update(item_agent='tv.plex.agents.series')
    True
    """
    if item_agent == 'tv.plex.agents.movie':
        return config.CONFIG['Themerr']['BOOL_PLEX_MOVIE_SUPPORT']
    elif item_agent == 'tv.plex.agents.series':
        return config.CONFIG['Themerr']['BOOL_PLEX_SERIES_SUPPORT']
    else:
        return False


def get_media_upload_path(item: PlexPartialObject, media_type: str) -> str:
    """
    Get the path to the theme upload directory.

    Get the hashed path of the theme upload directory for the item specified by the ``item``.

    Parameters
    ----------
    item : PlexPartialObject
        The item to get the theme upload path for.
    media_type : str
        The media type to get the theme upload path for. Must be one of 'art', 'posters', or 'themes'.

    Returns
    -------
    str
        The path to the theme upload directory.

    Raises
    ------
    ValueError
        If the ``media_type`` is not one of 'art', 'posters', or 'themes'.

    Examples
    --------
    >>> get_media_upload_path(item=..., media_type='art')
    "...bundle/Uploads/art..."
    >>> get_media_upload_path(item=..., media_type='posters')
    "...bundle/Uploads/posters..."
    >>> get_media_upload_path(item=..., media_type='themes')
    "...bundle/Uploads/themes..."
    """
    allowed_media_types = ['art', 'posters', 'themes']
    if media_type not in allowed_media_types:
        raise ValueError(
            'This error should be reported to https://github.com/LizardByte/Themerr-plex/issues;'
            f'media_type must be one of: {allowed_media_types}'
        )

    theme_upload_path = os.path.join(_get_metadata_path(item=item), 'Uploads', media_type)
    return theme_upload_path


def get_theme_provider(item: PlexPartialObject) -> Optional[str]:
    """
    Get the theme provider.

    Get the theme provider for the item specified by the ``item``.

    Parameters
    ----------
    item : PlexPartialObject
        The item to get the theme provider for.

    Returns
    -------
    str
        The theme provider.

    Examples
    --------
    >>> get_theme_provider(item=...)
    ...
    """
    provider_map = {
        'local': 'user',  # new agents, local media
        'com.plexapp.agents.localmedia': 'user',  # legacy agents, local media
        'com.plexapp.agents.plexthememusic': 'plex',  # legacy agents
    }

    rating_key_map = {
        'metadata://themes/tv.plex.agents.movies_': 'plex',  # new movie agent (placeholder if Plex adds theme support)
        'metadata://themes/tv.plex.agents.series_': 'plex',  # new tv agent
        'metadata://themes/com.plexapp.agents.plexthememusic_': 'plex',  # legacy agents
    }

    if not item.themes():
        log.debug(f'No themes found for item: {item.title}')
        return

    provider = None

    selected = None
    for theme in item.themes():
        if getattr(theme, 'selected'):
            selected = theme
            break
    if not selected:
        log.debug(f'No selected theme found for item: {item.title}')
        return

    if selected.provider in provider_map.keys():
        provider = provider_map[selected.provider]
    elif selected.ratingKey.startswith(tuple(rating_key_map.keys())):
        # new agents do not list a provider, so must match with rating keys if the theme

        # find the rating key prefix in the rating key map
        for rating_key_prefix in rating_key_map.keys():
            if selected.ratingKey.startswith(rating_key_prefix):
                provider = rating_key_map[rating_key_prefix]
                break
    else:
        provider = selected.provider

    if not provider:
        themerr_data = get_themerr_json_data(item=item)
        provider = 'themerr' if themerr_data else None

    return provider


def get_themerr_json_path(item: PlexPartialObject) -> str:
    """
    Get the path to the Themerr data file.

    Get the path to the Themerr data file for the item specified by the ``item``.

    Parameters
    ----------
    item : PlexPartialObject
        The item to get the Themerr data file path for.

    Returns
    -------
    str
        The path to the Themerr data file.

    Examples
    --------
    >>> get_themerr_json_path(item=...)
    '.../Plex Media Server/Plug-in Support/Data/dev.lizardbyte.themerr-plex/DataItems/...'
    """
    themerr_json_path = os.path.join(definitions.Paths.CONFIG_DIR, 'data', metadata_type_map[item.type],
                                     f'{item.ratingKey}.json')
    return themerr_json_path


def get_themerr_json_data(item: PlexPartialObject) -> dict:
    """
    Get the Themerr data for the specified item.

    Themerr data is stored as a JSON file in the Themerr data directory, and is used to ensure that we don't
    unnecessarily re-upload media to the Plex server.

    Parameters
    ----------
    item : PlexPartialObject
        The item to get the Themerr data for.

    Returns
    -------
    dict
        The Themerr data for the specified item, or empty dict if no Themerr data exists.
    """
    themerr_json_path = get_themerr_json_path(item=item)

    if os.path.isfile(themerr_json_path):
        themerr_data = json.loads(s=str(helpers.file_load(filename=themerr_json_path, binary=False)))
    else:
        themerr_data = dict()

    return themerr_data


def get_themerr_settings_hash() -> str:
    """
    Get a hash of the current Themerr settings.

    Returns
    -------
    str
        Hash of the current Themerr settings.

    Examples
    --------
    >>> get_themerr_settings_hash()
    '...'
    """
    # use to compare previous settings to new settings
    themerr_settings = dict(
        bool_prefer_mp4a_codec=config.CONFIG['Themerr']['BOOL_PREFER_MP4A_CODEC'],
        int_plexapi_plexapi_timeout=config.CONFIG['Themerr']['INT_PLEXAPI_PLEXAPI_TIMEOUT'],
    )
    settings_hash = hashlib.sha256(json.dumps(themerr_settings)).hexdigest()
    return settings_hash


def remove_uploaded_media(item: PlexPartialObject, media_type: str) -> None:
    """
    Remove themes for the specified item.

    Deletes the themes upload directory for the item specified by the ``item``.

    Parameters
    ----------
    item : PlexPartialObject
        The item to remove the themes from.
    media_type : str
        The media type to remove the themes from. Must be one of 'art', 'posters', or 'themes'.

    Returns
    -------
    py:class:`bool`
        True if the themes were removed successfully, False otherwise.

    Examples
    --------
    >>> remove_uploaded_media(item=..., media_type='themes')
    ...
    """
    theme_upload_path = get_media_upload_path(item=item, media_type=media_type)
    if os.path.isdir(theme_upload_path):
        shutil.rmtree(path=theme_upload_path, ignore_errors=True, onerror=remove_uploaded_media_error_handler)


def remove_uploaded_media_error_handler(func: any, path: any, exc_info: any) -> None:
    """
    Error handler for removing themes.

    Handles errors that occur when removing themes using ``shutil``.

    Parameters
    ----------
    func : any
        The function that caused the error.
    path : any
        The path that caused the error.
    exc_info : any
        The exception information.
    """
    log.error(f'Error removing themes with function: {func}, path: {path}, exception info: {exc_info}')


def update_themerr_data_file(item: PlexPartialObject, new_themerr_data: dict) -> None:
    """
    Update the Themerr data file for the specified item.

    This updates the themerr data file after uploading media to the Plex server.

    Parameters
    ----------
    item : PlexPartialObject
        The item to update the Themerr data file for.
    new_themerr_data : dict
        The Themerr data to update the Themerr data file with.
    """
    # get the old themerr data
    themerr_data = get_themerr_json_data(item=item)

    # remove legacy keys
    for key in legacy_keys:
        try:
            del themerr_data[key]
        except KeyError:
            pass

    # update the old themerr data with the new themerr data
    themerr_data.update(new_themerr_data)

    # get path
    themerr_json_path = get_themerr_json_path(item=item)

    # create directory if it doesn't exist
    if not os.path.isdir(os.path.dirname(themerr_json_path)):
        os.makedirs(os.path.dirname(themerr_json_path))

    # write themerr json
    helpers.file_save(filename=themerr_json_path, data=json.dumps(themerr_data), binary=False)