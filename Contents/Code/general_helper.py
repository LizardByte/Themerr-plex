# -*- coding: utf-8 -*-

# standard imports
import hashlib
import json
import os
import shutil

# plex debugging
try:
    import plexhints  # noqa: F401
except ImportError:
    pass
else:  # the code is running outside of Plex
    from plexhints.core_kit import Core  # core kit
    from plexhints.log_kit import Log  # log kit
    from plexhints.prefs_kit import Prefs  # prefs kit

# imports from Libraries\Shared
from plexapi.base import PlexPartialObject
import requests
from typing import Optional

# local imports
from constants import metadata_base_directory, metadata_type_map, themerr_data_directory

# constants
legacy_keys = [
    'downloaded_timestamp'
]


def get_media_upload_path(item, media_type):
    # type: (PlexPartialObject, str) -> str
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
            'media_type must be one of: {}'.format(allowed_media_types)
        )

    guid = item.guid
    full_hash = hashlib.sha1(guid).hexdigest()
    theme_upload_path = os.path.join(
        metadata_base_directory, metadata_type_map[item.type],
        full_hash[0], full_hash[1:] + '.bundle', 'Uploads', media_type)
    return theme_upload_path


def get_themerr_json_path(item):
    # type: (PlexPartialObject) -> str
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
    themerr_json_path = os.path.join(themerr_data_directory, metadata_type_map[item.type],
                                     '{}.json'.format(item.ratingKey))
    return themerr_json_path


def get_themerr_json_data(item):
    # type: (PlexPartialObject) -> dict
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
        themerr_data = json.loads(s=str(Core.storage.load(filename=themerr_json_path, binary=False)))
    else:
        themerr_data = dict()

    return themerr_data


def get_themerr_settings_hash():
    # type: () -> str
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
        bool_prefer_mp4a_codec=Prefs['bool_prefer_mp4a_codec'],
        int_plexapi_plexapi_timeout=Prefs['int_plexapi_plexapi_timeout'],
    )
    settings_hash = hashlib.sha256(json.dumps(themerr_settings)).hexdigest()
    return settings_hash


def get_user_country_code(ip_address=None):
    # type: (Optional[str]) -> str
    """
    Get the country code for the user with the given IP address.

    Parameters
    ----------
    ip_address : Optional[str]
        The IP address of the user.

    Returns
    -------
    str
        The `ALPHA-2 <https://www.iban.com/country-codes>`__ country code for the user with the given IP address.

    Examples
    --------
    >>> get_user_country_code()
    'US'
    """
    api_url = 'https://ipinfo.io/json'
    if ip_address:
        api_url = 'https://ipinfo.io/{}/json'.format(ip_address)

    try:
        response = requests.get(api_url)
        data = response.json()
        return data.get('country').encode('utf-8')
    except requests.RequestException as e:
        Log.Error("Could not determine user country: {}".format(e))


def is_user_in_eu(ip_address=None):
    # type: (Optional[str]) -> bool
    """
    Check if the user with the given IP address is in the European Union.

    Parameters
    ----------
    ip_address : Optional[str]
        The IP address of the user.

    Returns
    -------
    bool
        True if the user with the given IP address is in the European Union, False otherwise.

    Examples
    --------
    >>> is_user_in_eu()
    False
    """
    eu_countries = [
        'AT',  # Austria
        'BE',  # Belgium
        'BG',  # Bulgaria
        'CY',  # Cyprus
        'CZ',  # Czech Republic
        'DE',  # Germany
        'DK',  # Denmark
        'EE',  # Estonia
        'ES',  # Spain
        'FI',  # Finland
        'FR',  # France
        'GR',  # Greece
        'HR',  # Croatia
        'HU',  # Hungary
        'IE',  # Ireland
        'IT',  # Italy
        'LT',  # Lithuania
        'LU',  # Luxembourg
        'LV',  # Latvia
        'MT',  # Malta
        'NL',  # Netherlands
        'PL',  # Poland
        'PT',  # Portugal
        'RO',  # Romania
        'SE',  # Sweden
        'SI',  # Slovenia
        'SK',  # Slovakia
    ]

    country_code = get_user_country_code(ip_address=ip_address)
    return country_code in eu_countries


def remove_uploaded_media(item, media_type):
    # type: (PlexPartialObject, str) -> None
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
    bool
        True if the themes were removed successfully, False otherwise.

    Examples
    --------
    >>> remove_uploaded_media(item=..., media_type='themes')
    ...
    """
    theme_upload_path = get_media_upload_path(item=item, media_type=media_type)
    if os.path.isdir(theme_upload_path):
        shutil.rmtree(path=theme_upload_path, ignore_errors=True, onerror=remove_uploaded_media_error_handler)


def remove_uploaded_media_error_handler(func, path, exc_info):
    # type: (any, any, any) -> None
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
    Log.Error('Error removing themes with function: %s, path: %s, exception info: %s' % (func, path, exc_info))


def update_themerr_data_file(item, new_themerr_data):
    # type: (PlexPartialObject, dict) -> None
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
    Core.storage.save(filename=themerr_json_path, data=json.dumps(themerr_data), binary=False)
