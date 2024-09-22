"""
src/common/config.py

Responsible for config related functions.
"""
# standard imports
import base64
import copy
import sys
from typing import Optional, List

# lib imports
from configobj import ConfigObj
from validate import Validator, ValidateError

# local imports
from common import definitions
from common import logger
from common import locales

# get log
log = logger.get_logger(name=__name__)

# get the config filename
FILENAME = definitions.Files.CONFIG

# access the config dictionary here
CONFIG = None

# localization
_ = locales.get_text()

# increase CONFIG_VERSION default and max when changing default values
# then do `if CONFIG_VERSION == x:` something to change the old default value to the new default value
# then update the CONFIG_VERSION number


# https://regexpattern.com/windows-folder-path/
# https://regexpattern.com/linux-folder-path/
regex_directory = r'^[a-zA-Z]:\\(?:\w+\\?)*$' if definitions.Platform.os_platform == 'win32' else r'^\/(?:[^/]+\/)*$'


def on_change_tray_toggle() -> bool:
    """
    Toggle the tray icon.

    This is needed, since ``tray_icon`` cannot be imported at the module level without a circular import.

    Returns
    -------
    bool
        ``True`` if successful, otherwise ``False``.

    See Also
    --------
    common.tray_icon.tray_toggle : ``on_change_tray_toggle`` is an alias of this function.

    Examples
    --------
    >>> on_change_tray_toggle()
    True
    """
    from common import tray_icon
    return tray_icon.tray_toggle()


# types
# - section
# - boolean
# - option
# - string
# - integer
# - float
# data parsley types (Parsley validation)
# - alphanum (string)
# - email (string)
# - url (string)
# - number (float, integer)
# - integer (integer)
# - digits (string)
_CONFIG_SPEC_DICT = dict(
    Info=dict(
        type='section',
        name=_('Info'),
        description=_('For information purposes only.'),
        icon='info',
        CONFIG_VERSION=dict(
            type='integer',
            name=_('Config version'),
            description=_('The configuration version.'),
            default=0,  # increment when updating config
            min=0,
            max=0,  # increment when updating config
            data_parsley_type='integer',
            extra_class='col-md-3',
            locked=True,
        ),
        FIRST_RUN_COMPLETE=dict(
            type='boolean',
            name=_('First run complete'),
            description=_('Todo: Indicates if the user has completed the initial setup.'),
            default=False,
            locked=True,
        ),
    ),
    General=dict(
        type='section',
        name=_('General'),
        description=_('General settings.'),
        icon='gear',
        LOCALE=dict(
            type='option',
            name=_('Locale'),
            description=_('The localization setting to use.'),
            default='en',
            options=[
                'de',
                'en',
                'en_GB',
                'en_US',
                'es',
                'fr',
                'it',
                'ja',
                'pt',
                'ru',
                'sv',
                'tr',
                'zh',
            ],
            option_names=[
                f'German ({_("German")})',
                f'English ({_("English")})',
                f'English (Great Britain) ({_("English (Great Britain)")})',
                f'English (United States) ({_("English (United States)")})',
                f'Spanish ({_("Spanish")})',
                f'French ({_("French")})',
                f'Italian ({_("Italian")})',
                f'Japanese ({_("Japanese")})',
                f'Portuguese ({_("Portuguese")})',
                f'Russian ({_("Russian")})',
                f'Swedish ({_("Swedish")})',
                f'Turkish ({_("Turkish")})',
                f'Chinese (Simplified) ({_("Chinese (Simplified)")})',
            ],
            refresh=True,
            extra_class='col-lg-6',
        ),
        LAUNCH_BROWSER=dict(
            type='boolean',
            name=_('Launch Browser on Startup '),
            description=_(f'Open browser when {definitions.Names.name} starts.'),
            default=True,
        ),
        SYSTEM_TRAY=dict(
            type='boolean',
            name=_('Enable System Tray Icon'),
            description=_(f'Show {definitions.Names.name} shortcut in the system tray.'),
            default=True,
            # todo - fix circular import
            on_change=on_change_tray_toggle,
        ),
    ),
    Logging=dict(
        type='section',
        name=_('Logging'),
        description=_('Logging settings.'),
        icon='file-code',
        LOG_DIR=dict(
            type='string',
            name=_('Log directory'),
            advanced=True,
            description=_('The directory where to store the log files.'),
            data_parsley_pattern=regex_directory,
            extra_class='col-lg-8',
            button_directory=True,
        ),
        DEBUG_LOGGING=dict(
            type='boolean',
            name=_('Debug logging'),
            advanced=True,
            description=_('Enable debug logging.'),
            default=True,
        ),
    ),
    Network=dict(
        type='section',
        name=_('Network'),
        description=_('Network settings.'),
        icon='network-wired',
        HTTP_HOST=dict(
            type='string',
            name=_('HTTP host address'),
            advanced=True,
            description=_('The HTTP address to bind to.'),
            default='0.0.0.0',
            data_parsley_pattern=r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)[.]){3}'
                                 r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b',
            # https://codverter.com/blog/articles/tech/20190105-extract-ipv4-ipv6-ip-addresses-using-regex.html
            extra_class='col-md-4',
        ),
        HTTP_PORT=dict(
            type='integer',
            name=_('HTTP port'),
            advanced=True,
            description=_('Port to bind web server to. Note that ports below 1024 may require root.'),
            default=9494,
            min=21,
            max=65535,
            data_parsley_type='integer',
            extra_class='col-md-3',
        ),
        HTTP_ROOT=dict(
            type='string',
            name=_('HTTP root'),
            beta=True,
            description=_('Todo: The base URL of the web server. Used for reverse proxies.'),
            extra_class='col-lg-6',
        ),
        SSL=dict(
            type='boolean',
            name=_('SSL'),
            default=True,
            description=_('Run the web server with HTTPS. '
                          'Disabling this can be a security risk, do so at your own risk.'),
        ),
    ),
    User_Interface=dict(
        type='section',
        name=_('User Interface'),
        description=_('User interface settings.'),
        icon='display',
        BACKGROUND_VIDEO=dict(
            type='boolean',
            name=_('Background video'),
            description=_('Enable background video.'),
            default=True,
        ),
    ),
    Updater=dict(
        type='section',
        name=_('Updater'),
        description=_('Updater settings.'),
        icon='arrows-spin',
        AUTO_UPDATE=dict(
            type='boolean',
            name=_('Auto update'),
            beta=True,
            description=_(f'Todo: Automatically update {definitions.Names.name}.'),
            default=False,
        ),
    ),
    Plex=dict(
        type='section',
        name=_('Plex'),
        description=_('Plex settings.'),
        icon='chevron-right',
        PLEX_URL=dict(
            type='string',
            name=_('Plex URL'),
            description=_('The URL to the Plex server.'),
            default='http://127.0.0.1:32400',
            data_parsley_pattern=r'^https?:\/\/(?:[a-zA-Z0-9-]+\.?)+(:\d{1,5})?$',
            extra_class='col-lg-6',
        ),
        PLEX_TOKEN=dict(
            type='string',
            name=_('Plex token'),
            mask=True,
            description=_('The Plex token.'),
            data_parsley_type='alphanum',
            extra_class='col-lg-6',
        ),
        PLEX_APP_SUPPORT_PATH=dict(
            type='string',
            name=_('Plex data directory'),
            description=_('https://support.plex.tv/articles/'
                          '202915258-where-is-the-plex-media-server-data-directory-located/'),
            data_parsley_pattern=regex_directory,
            extra_class='col-lg-8',
            button_directory=True,
        ),
    ),
    Themerr=dict(
        type='section',
        name=_('Themerr'),
        description=_('Themerr settings.'),
        icon='music',
        BOOL_THEMERR_ENABLED=dict(
            type='boolean',
            name=_('Themerr Enabled'),
            description=_('When enabled, Themerr will attempt to update themes.'),
            default=True,
        ),
        BOOL_PLEX_COLLECTION_SUPPORT=dict(
            type='boolean',
            name=_('Collections'),
            description=_('Add themes to collections.'),
            default=True,
        ),
        BOOL_PLEX_MOVIE_SUPPORT=dict(
            type='boolean',
            name=_('Movie support'),
            description=_('Add themes to movies using the Plex Movie agent.'),
            default=True,
        ),
        BOOL_PLEX_SERIES_SUPPORT=dict(
            type='boolean',
            name=_('Series support'),
            description=_('Add themes to series using the Plex Series agent.'),
            default=True,
        ),
        BOOL_OVERWRITE_PLEX_PROVIDED_THEMES=dict(
            type='boolean',
            name=_('Overwrite Plex themes'),
            description=_('When enabled, Themerr will overwrite themes provided by Plex.'),
            default=True,
        ),
        BOOL_PREFER_MP4A_CODEC=dict(
            type='boolean',
            name=_('Prefer MP4A AAC Codec'),
            description=_('This can improve theme compatibility with Apple devices.'),
            default=True,
        ),
        BOOL_REMOVE_UNUSED_THEMES=dict(
            type='boolean',
            name=_('Remove unused themes'),
            description=_('Frees up space in your Plex metadata directory. '
                          'This option requires that the "Plex data directory" path is set'),
            default=True,
        ),
        BOOL_REMOVE_UNUSED_ART=dict(
            type='boolean',
            name=_('Remove unused art'),
            description=_('Applies to collection. '
                          'Frees up space in your Plex metadata directory. '
                          'This option requires that the "Plex data directory" path is set'),
            default=True,
        ),
        BOOL_REMOVE_UNUSED_POSTERS=dict(
            type='boolean',
            name=_('Remove unused posters'),
            description=_('Applies to collection. '
                          'Frees up space in your Plex metadata directory. '
                          'This option requires that the "Plex data directory" path is set'),
            default=True,
        ),
        BOOL_UPDATE_COLLECTION_METADATA=dict(
            type='boolean',
            name=_('Collection metadata'),
            description=_('Update collection metadata (poster, art, and summary) during scheduled update.'),
            default=False,
        ),
        BOOL_IGNORE_LOCKED_FIELDS=dict(
            type='boolean',
            name=_('Ignore locked fields.'),
            description=_('If you used Themerr-plex v2024.813.13709 or lower, '
                          'you may need to enable this to update items.'),
            default=False,
        ),
        INT_UPDATE_THEMES_INTERVAL=dict(
            type='integer',
            name=_('Update themes interval'),
            description=_('Interval for automatic update task, in minutes (min: 15).'),
            default=60,
            advanced=True,
            extra_class='col-md-2',
        ),
        INT_UPDATE_DATABASE_CACHE_INTERVAL=dict(
            type='integer',
            name=_('Update database cache interval'),
            description=_('Interval for database cache update task, in minutes (min: 15).'),
            default=60,
            advanced=True,
            extra_class='col-md-2',
        ),
        INT_PLEXAPI_PLEXAPI_TIMEOUT=dict(
            type='integer',
            name=_('PlexAPI timeout'),
            description=_('Increase this slightly if you experience timeouts when adding themes. (min: 1)'),
            default=180,
            advanced=True,
            extra_class='col-md-2',
        ),
        INT_PLEXAPI_UPLOAD_RETRIES_MAX=dict(
            type='integer',
            name=_('Theme upload retries'),
            description=_('If uploading themes fail, retry this many times. (min: 0)'),
            default=3,
            advanced=True,
            extra_class='col-md-2',
        ),
        INT_PLEXAPI_UPLOAD_THREADS=dict(
            type='integer',
            name=_('Multiprocessing thread count'),
            description=_('The number of threads to use when adding themes. (min: 1)'),
            default=3,
            advanced=True,
            extra_class='col-md-2',
        ),
        STR_YOUTUBE_COOKIES=dict(
            type='string',
            name=_('YouTube Cookies'),
            description=_('Using cookies may improve the success rate of downloading themes. (JSON format)'),
            advanced=True,
        ),
    ),
)


def is_masked_field(section: str, key: str) -> bool:
    """
    Check if a field is masked.

    This function will check if a field is masked in the config spec dictionary.

    Parameters
    ----------
    section : str
        The section of the config.
    key : str
        The key of the config field.

    Returns
    -------
    bool
        True if the field is masked, otherwise False.

    Examples
    --------
    >>> is_masked_field(section='General', key='API_KEY')
    True
    """
    return _CONFIG_SPEC_DICT.get(section, {}).get(key, {}).get('mask', False)


def encode_value(value: str) -> str:
    """
    Encode a value using base64.

    This function will encode a value using base64.

    Parameters
    ----------
    value : str
        The value to encode.

    Returns
    -------
    str
        The encoded value.

    Examples
    --------
    >>> encode_value('some text')
    'c29tZSB0ZXh0'
    """
    return base64.b64encode(value.encode('utf-8')).decode('utf-8')


def decode_value(value: str) -> str:
    """
    Decode a base64 encoded value.

    This function will decode a base64 encoded value.

    Parameters
    ----------
    value : str
        The value to decode.

    Returns
    -------
    str
        The decoded value. If the value cannot be decoded, an empty string is returned.

    Examples
    --------
    >>> decode_value('c29tZSB0ZXh0')
    'some text'
    """
    try:
        return base64.b64decode(value.encode('utf-8')).decode('utf-8')
    except Exception as e:
        log.error(msg=f"Unable to decode value: {e}")
        return ''


def decode_config(config: ConfigObj) -> dict:
    """
    Decode masked fields in the config.

    This function will create a decoded copy of the config object, and decode any masked fields.

    Parameters
    ----------
    config : ConfigObj
        The config object to decode.

    Returns
    -------
    dict
        A decoded copy of the config object.

    Examples
    --------
    >>> config_object = create_config(config_file='config.ini')
    >>> decode_config(config=config_object)
    {...}
    """
    _config = copy.deepcopy(config)  # we need to do a deepcopy to avoid modifying the original config

    for section, options in _config.items():
        for key, value in options.items():
            if is_masked_field(section=section, key=key):
                _config[section][key] = decode_value(value)
    return _config


def convert_config(d: dict = _CONFIG_SPEC_DICT, _config_spec: Optional[List] = None) -> List:
    """
    Convert a config spec dictionary to a config spec list.

    A config spec dictionary is a custom type of dictionary that will be converted into a standard config spec list
    which can later be used by ``configobj``.

    Parameters
    ----------
    d : dict
        The dictionary to convert.
    _config_spec : Optional[List]
        This should not be set when using this function, but since this function calls itself it needs to pass in the
        list that is being built in order to return the correct list.

    Returns
    -------
    list
        A list representing a configspec for ``configobj``.

    Examples
    --------
    >>> convert_config(d=_CONFIG_SPEC_DICT)
    [...]
    """
    if _config_spec is None:
        _config_spec = []

    for k, v in d.items():
        try:
            v['type']
        except TypeError:
            pass
        else:
            # if a default value is not set, then set it to None
            if 'default' not in v:
                v['default'] = ''

            checks = ['min', 'max', 'options', 'default']
            check_value = ''

            for check in checks:
                try:
                    v[check]
                except KeyError:
                    pass
                else:
                    check_value += f"{', ' if check_value != '' else ''}"
                    if check == 'options':
                        for option_value in v[check]:
                            if check_value:
                                check_value += f"{', ' if not check_value.endswith(', ') else ''}"
                            if isinstance(option_value, str):
                                check_value += f'"{option_value}"'
                            else:
                                check_value += f'{option_value}'
                    elif isinstance(v[check], str):
                        check_value += f"{check}=\"{v[check]}\""
                    else:
                        check_value += f"{check}={v[check]}"

            check_value = f'({check_value})' if check_value else ''  # add parenthesis if there's a value

            if v['type'] == 'section':  # config section
                _config_spec.append(f'[{k}]')
            else:  # int option
                _config_spec.append(f"{k} = {v['type']}{check_value}")

        if isinstance(v, dict):
            # continue parsing nested dictionary
            convert_config(d=v, _config_spec=_config_spec)

    return _config_spec


def create_config(config_file: str, config_spec: dict = _CONFIG_SPEC_DICT) -> ConfigObj:
    """
    Create a config file and `ConfigObj` using a config spec dictionary.

    A config spec dictionary is a strictly formatted dictionary that will be converted into a standard config spec list
    to be later used by ``configobj``.

    The created config is validated against a Validator object. This function will remove keys from the user's
    config.ini if they no longer exist in the config spec.

    Parameters
    ----------
    config_file : str
        Full filename of config file.
    config_spec : dict, default = _CONFIG_SPEC_DICT
        Config spec to use.

    Returns
    -------
    ConfigObj
        Dictionary of config keys and values.

    Raises
    ------
    SystemExit
        If config_spec is not valid.

    Examples
    --------
    >>> create_config(config_file='config.ini')
    ConfigObj({...})
    """
    # convert config spec dictionary to list
    config_spec_list = convert_config(d=config_spec)

    config = ConfigObj(
        configspec=config_spec_list,
        encoding='UTF-8',
        list_values=True,
        stringify=True,
        write_empty_values=False,
    )
    config_valid = validate_config(config=config)

    if not config_valid:
        # logger may not be initialized
        log_msg = "Unable to initialize due to a corrupted config spec. Exiting..."
        log.error(msg=log_msg)
        raise SystemExit(log_msg)

    user_config = ConfigObj(
        infile=config_file,
        configspec=config_spec_list,
        encoding='UTF-8',
        list_values=True,
        stringify=True,
        write_empty_values=False,
    )
    user_config_valid = validate_config(config=user_config)
    if not user_config_valid:
        # write to stderr and logger
        log_msg = "Invalid 'config.ini' file, attempting to correct.\n"
        log.error(msg=log_msg)
        sys.stderr.write(log_msg)

    # dictionary comprehension
    if config_valid and user_config_valid:
        # remove values from user config that are no longer in the spec
        user_config = {
            key: {
                k: v for k, v in value.items() if k in config.get(key, {})
            } for key, value in user_config.items()
        }

        # remove sections from user config that are no longer in the spec
        user_config = {key: value for key, value in user_config.items() if key in config}

        # merge user config into default config
        config.merge(indict=user_config)

        # validate merged config
        validate_config(config=config)

    config.filename = config_file
    save_config(config=config)

    if config_spec == _CONFIG_SPEC_DICT:  # set CONFIG dictionary
        global CONFIG
        CONFIG = config

    return config


def save_config(config: ConfigObj = CONFIG) -> bool:
    """
    Save the config to file.

    Saves the `ConfigObj` to the specified file.

    Parameters
    ----------
    config : ConfigObj, default = CONFIG
        Config to save.

    Returns
    -------
    bool
        True if save successful, otherwise False.

    Examples
    --------
    >>> config_object = create_config(config_file='config.ini')
    >>> save_config(config=config_object)
    True
    """
    try:
        config.write()
    except Exception:
        return False
    else:
        return True


def validate_config(config: ConfigObj) -> bool:
    """
    Validate ConfigObj dictionary.

    Ensures that the given `ConfigObj` is valid.

    Parameters
    ----------
    config : ConfigObj
        Config to validate.

    Returns
    -------
    bool
        True if validation passes, otherwise False.

    Examples
    --------
    >>> config_object = create_config(config_file='config.ini')
    >>> validate_config(config=config_object)
    True
    """
    validator = Validator()
    try:
        config.validate(
            validator=validator,
            copy=False  # don't write out default values
        )
        return True
    except ValidateError as e:
        log_msg = f"Config validation error: {e}.\n"
        log.error(msg=log_msg)
        sys.stderr.write(log_msg)
        return False
