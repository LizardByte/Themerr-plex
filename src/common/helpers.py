"""
src/common/helpers.py

Many reusable helper functions.
"""
# standard imports
import datetime
import json
import logging
import os
import requests
import requests_cache
import time
from typing import AnyStr, Optional, Union
from urllib.parse import quote, quote_plus, unquote, unquote_plus
import webbrowser


def check_folder_writable(fallback: str, name: str, folder: Optional[str] = None) -> tuple[str, Optional[bool]]:
    """
    Check if folder or fallback folder is writeable.

    This function ensures that the folder can be created, if it doesn't exist. It also ensures there are sufficient
    permissions to write to the folder. If the primary `folder` fails, it falls back to the `fallback` folder.

    Parameters
    ----------
    fallback : str
        Secondary folder to check, if the primary folder fails.
    name : str
        Short name of folder.
    folder : str, optional
        Primary folder to check.

    Returns
    -------
    tuple[str, Optional[bool]]
        A tuple containing:
            folder : str
                The original or fallback folder.
            Optional[bool]
                True if writeable, otherwise False. Nothing is returned if there is an error attempting to create the
                directory.

    Examples
    --------
    >>> check_folder_writable(
    ...     folder='logs',
    ...     fallback='backup_logs',
    ...     name='logs'
    ...     )
    ('logs', True)
    """
    if not folder:
        folder = fallback

    try:
        os.makedirs(name=folder, exist_ok=True)
    except OSError as e:
        log.error(msg=f"Could not create {name} dir '{folder}': {e}")
        if fallback and folder != fallback:
            log.warning(msg=f"Falling back to {name} dir '{fallback}'")
            return check_folder_writable(folder=None, fallback=fallback, name=name)
        else:
            return folder, None

    if not os.access(path=folder, mode=os.W_OK):
        log.error(msg=f"Cannot write to {name} dir '{folder}'")
        if fallback and folder != fallback:
            log.warning(msg=f"Falling back to {name} dir '{fallback}'")
            return check_folder_writable(folder=None, fallback=fallback, name=name)
        else:
            return folder, False

    return folder, True


def docker_healthcheck() -> bool:
    """
    Check the health of the docker container.

    .. Warning:: This is only meant to be called by `themerr-plex.py`, and the interpreter should be immediate exited
       following the result.

    The default port is used considering that the container will use the default port internally.
    The external port should not make any difference.

    Returns
    -------
    bool
        True if status okay, otherwise False.

    Examples
    --------
    >>> docker_healthcheck()
    True
    """
    protocols = ['http', 'https']

    for p in protocols:
        try:
            response = requests.get(url=f'{p}://localhost:9696/status')
        except requests.exceptions.ConnectionError:
            pass
        else:
            if response.status_code == 200:
                return True

    return False  # did not get a valid response, so return False


def file_load(filename: str, binary: bool = False) -> Optional[AnyStr]:
    """
    Open a file and return the contents.

    This function will open a file and return the contents. If the file does not exist, None is returned.

    Parameters
    ----------
    filename : str
        The file to open.
    binary : bool, default = False
        True to open the file in binary mode.

    Returns
    -------
    Optional[AnyStr]
        The contents of the file, or None if the file does not exist.

    Examples
    --------
    >>> file_load(filename='file.txt')
    'This is the contents of the file.'
    """
    mode = 'rb' if binary else 'r'
    try:
        with open(file=filename, mode=mode) as f:
            return f.read()
    except Exception as e:
        log.error(f'Error loading data from {filename}: {e}')
    return None


def file_save(filename: str, data: AnyStr, binary: bool = False) -> bool:
    """
    Save data to a file.

    This function will save the given data to a file.

    Parameters
    ----------
    filename : str
        The file to save the data to.
    data : AnyStr
        The data to save.
    binary : bool, default = False
        True to save the data in binary mode.

    Returns
    -------
    bool
        True if successful, otherwise False.

    Examples
    --------
    >>> file_save(filename='file.txt', data='This is the contents of the file.')
    True
    """
    mode = 'wb' if binary else 'w'
    try:
        with open(file=filename, mode=mode) as f:
            f.write(data)
    except Exception as e:
        log.error(f'Error saving data to {filename}: {e}')
        return False
    else:
        return True


def get_logger(name: str) -> logging.Logger:
    """
    Get the logger for the given name.

    This function also exists in `logger.py` to prevent circular imports.

    Parameters
    ----------
    name : str
        Name of logger.

    Returns
    -------
    logging.Logger
        The logging.Logger object.

    Examples
    --------
    >>> get_logger(name='my_log')
    <Logger my_log (WARNING)>
    """
    return logging.getLogger(name=name)


def json_get(
        url: str,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
        cache_time: int = 0,
        sleep_time: Union[float, int] = 0.0,
        request_type: str = 'get',
) -> dict:
    """
    Get JSON data from a URL.

    This function will get JSON data from a URL, with optional headers and parameters.

    Parameters
    ----------
    url : str
        The URL to get JSON data from.
    headers : Optional[dict]
        Optional headers to send with the request.
    params : Optional[dict]
        Optional parameters to send with the request.
    cache_time : int, default = 0
        Time in seconds to cache the data.
    sleep_time : Union[float, int], default = 0.0
        Time in seconds to sleep before making the request.
    request_type : str, default = 'get'
        The type of request to make. Valid options are 'get' and 'post'.

    Returns
    -------
    dict
        The JSON data from the URL. If there is an error, an empty dictionary is returned.

    Examples
    --------
    >>> json_get(url='https://www.example.com')
    {...}
    """
    if cache_time > 0:
        session = requests_cache.CachedSession(cache_name='http_cache', expire_after=cache_time)
    else:
        session = requests.Session()

    if sleep_time > 0:
        time.sleep(sleep_time)

    type_map = {
        'get': session.get,
        'post': session.post,
    }

    request_type = request_type.lower()
    if request_type not in type_map:
        log.error(f'Invalid request type: {request_type}')
        return {}

    try:
        request = type_map[request_type](url=url, headers=headers, params=params)
    except requests.exceptions.RequestException as e:
        log.error(f'Error getting JSON data from {url}: {e}')
        return {}
    else:
        try:
            data = request.json()
        except json.JSONDecodeError as e:
            log.error(f'Error decoding JSON data from {url}: {e}')
            return {}

        return data


def now(separate: bool = False) -> str:
    """
    Function to get the current time, formatted.

    This function will return the current time formatted as YMDHMS

    Parameters
    ----------
    separate : bool, default = False
        True to separate time with a combination of dashes (`-`) and colons (`:`).

    Returns
    -------
    str
        The current time formatted as YMDHMS.

    Examples
    --------
    >>> now()
    '20220410184531'

    >>> now(separate=True)
    '2022-04-10 18:46:12'
    """
    return timestamp_to_YMDHMS(ts=timestamp(), separate=separate)


def open_url_in_browser(url: str) -> bool:
    """
    Open a given url in the default browser.

    Attempt to open the given url in the default web browser, in a new tab.

    Parameters
    ----------
    url : str
        The url to open.

    Returns
    -------
    bool
        True if no error, otherwise False.

    Examples
    --------
    >>> open_url_in_browser(url='https://www.google.com')
    True
    """
    try:
        webbrowser.open(url=url, new=2)
    except webbrowser.Error:
        return False
    else:
        return True


def string_quote(string: str, use_plus: bool = False) -> str:
    """
    Quote a string.

    This function will quote a string, replacing spaces with either `+` or `%20`.

    Parameters
    ----------
    string : str
        The string to quote.
    use_plus : bool, default = False
        True to replace spaces with `+`, otherwise `%20`.

    Returns
    -------
    str
        The quoted string.

    Examples
    --------
    >>> string_quote(string='This is a string')
    'This%20is%20a%20string'

    >>> string_quote(string='This is a string', use_plus=True)
    'This+is+a+string'
    """
    if use_plus:
        return quote_plus(string)
    return quote(string)


def string_unquote(string: str, use_plus: bool = False) -> str:
    """
    Unquote a string.

    This function will unquote a string, replacing `+` or `%20` with spaces.

    Parameters
    ----------
    string : str
        The string to unquote.
    use_plus : bool, default = False
        True to replace `+` with spaces, otherwise `%20`.

    Returns
    -------
    str
        The unquoted string.

    Examples
    --------
    >>> string_unquote(string='This%20is%20a%20string')
    'This is a string'

    >>> string_unquote(string='This+is+a+string', use_plus=True)
    'This is a string'
    """
    if use_plus:
        return unquote_plus(string)
    return unquote(string)


def timestamp() -> int:
    """
    Function to get the current time.

    This function uses time.time() to get the current time.

    Returns
    -------
    int
        The current time as a timestamp integer.

    Examples
    --------
    >>> timestamp()
    1649631005
    """
    return int(time.time())


def timestamp_to_YMDHMS(ts: int, separate: bool = False) -> str:
    """
    Convert timestamp to YMDHMS format.

    Convert a given timestamp to YMDHMS format.

    Parameters
    ----------
    ts : int
        The timestamp to convert.
    separate : bool, default = False
        True to separate time with a combination of dashes (`-`) and colons (`:`).

    Returns
    -------
    str
        The timestamp formatted as YMDHMS.

    Examples
    --------
    >>> timestamp_to_YMDHMS(ts=timestamp(), separate=False)
    '20220410185142'

    >>> timestamp_to_YMDHMS(ts=timestamp(), separate=True)
    '2022-04-10 18:52:09'
    """
    dt = timestamp_to_datetime(ts=ts)
    if separate:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return dt.strftime("%Y%m%d%H%M%S")


def timestamp_to_datetime(ts: float) -> datetime.datetime:
    """
    Convert timestamp to datetime object.

    This function returns the result of `datetime.datetime.fromtimestamp()`.

    Parameters
    ----------
    ts : float
        The timestamp to convert.

    Returns
    -------
    datetime.datetime
        Object `datetime.datetime`.

    Examples
    --------
    >>> timestamp_to_datetime(ts=timestamp())
    datetime.datetime(20..., ..., ..., ..., ..., ...)
    """
    return datetime.datetime.fromtimestamp(ts)


# get logger
log = get_logger(name=__name__)
