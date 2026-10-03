"""
src/common/logger.py

Responsible for logging related functions.
"""
# standard imports
import contextlib
import errno
import logging
import multiprocessing
import os
import re
import sys
import threading
import traceback
from logging import handlers
from logging.handlers import QueueHandler, QueueListener

# lib imports
from configobj import ConfigObj

# local imports
import common
from common import definitions
from common import helpers

# These settings are for file logging only
app_name = 'themerr'
LOG_NAMES = ('themerr', 'backend', 'yt-dlp')
MAX_SIZE = 5000000  # 5 MB
MAX_FILES = 5

# used for log filters
_BLACKLIST_KEYS = ['_APITOKEN', '_TOKEN', '_KEY', '_SECRET', '_PASSWORD', '_APIKEY', '_ID', '_HOOK']
_WHITELIST_KEYS = ['HTTPS_KEY']

LOG_BLACKLIST = [True]

_BLACKLIST_WORDS = set()
_session_handler = None

# Global queue for multiprocessing logging
queue = None


def blacklist_config(config: ConfigObj):
    """
    Update blacklist words.

    In order to filter words out of the logs, it is required to call this function.

    Values in the config for keys containing the following terms will be removed.

    - HOOK
    - APIKEY
    - KEY
    - PASSWORD
    - TOKEN

    Parameters
    ----------
    config : ConfigObj
        Config to parse.

    Examples
    --------
    >>> config_object = common.config.create_config(config_file='config.ini')
    >>> blacklist_config(config=config_object)
    """
    blacklist = set()
    blacklist_keys = ['HOOK', 'APIKEY', 'KEY', 'PASSWORD', 'TOKEN', 'STR_YOUTUBE_COOKIES']

    for k, v in config.items():
        for key, value in v.items():
            if isinstance(value, str) and len(value.strip()) > 5 and \
                    key.upper() not in _WHITELIST_KEYS and (key.upper() in blacklist_keys or
                                                            any(bk in key.upper() for bk in _BLACKLIST_KEYS)):
                blacklist.add(value.strip())

    _BLACKLIST_WORDS.update(blacklist)


class NoThreadFilter(logging.Filter):
    """
    Log filter for the current thread.

    .. todo:: This documentation needs to be improved.

    Parameters
    ----------
    thread_name : str
        The name of the thread.

    Methods
    -------
    filter:
        Filter the given record.

    Examples
    --------
    >>> NoThreadFilter('main')
    <common.logger.NoThreadFilter object at 0x...>
    """

    def __init__(self, thread_name):
        super(NoThreadFilter, self).__init__()

        self.threadName = thread_name

    def filter(self, record) -> bool:
        """
        Filter the given record.

        .. todo:: This documentation needs to be improved.

        Parameters
        ----------
        record : NoThreadFilter
            The record to filter.

        Returns
        -------
        bool
            True if record.threadName is not equal to self.threadName, otherwise False.

        Examples
        --------
        >>> NoThreadFilter('main').filter(record=NoThreadFilter('test'))
        True

        >>> NoThreadFilter('main').filter(record=NoThreadFilter('main'))
        False
        """
        return record.threadName != self.threadName


# Taken from Hellowlol/HTPC-Manager
class BlacklistFilter(logging.Filter):
    """
    Filter logs for blacklisted words.

    Log filter for blacklisted tokens and passwords.

    Methods
    -------
    filter:
        Filter the given record.

    Examples
    --------
    >>> BlacklistFilter()
    <common.logger.BlacklistFilter object at 0x...>
    """

    def __init__(self):
        super(BlacklistFilter, self).__init__()

    def filter(self, record) -> bool:
        """
        Filter the given record.

        .. todo:: This documentation needs to be improved.

        Parameters
        ----------
        record : BlacklistFilter
            The record to filter.

        Returns
        -------
        bool
            True in all cases.

        Examples
        --------
        >>> BlacklistFilter().filter(record=BlacklistFilter())
        True
        """
        if not LOG_BLACKLIST:
            return super().filter(record)

        for item in _BLACKLIST_WORDS:
            try:
                if item in record.msg:
                    record.msg = record.msg.replace(item, 16 * '*')

                args = []
                for arg in record.args:
                    try:
                        arg_str = str(arg)
                        if item in arg_str:
                            arg_str = arg_str.replace(item, 16 * '*')
                            arg = arg_str
                    except Exception:
                        pass
                    args.append(arg)
                record.args = tuple(args)
            except Exception:
                pass

        return super().filter(record)


class RegexFilter(logging.Filter):
    """
    Base class for regex log filter.

    Log filter for regex.

    Attributes
    ----------
    regex : re.compile
        The compiled regex pattern.

    Methods
    -------
    filter:
        Filter the given record.

    Examples
    --------
    >>> RegexFilter()
    <common.logger.RegexFilter object at 0x...>
    """

    def __init__(self):
        super(RegexFilter, self).__init__()

        self.regex = re.compile(pattern=r'')

    def filter(self, record) -> bool:
        """
        Filter the given record.

        .. todo:: This documentation needs to be improved.

        Parameters
        ----------
        record : RegexFilter
            The record to filter.

        Returns
        -------
        bool
            True in all cases.

        Examples
        --------
        >>> RegexFilter().filter(record=RegexFilter())
        True
        """
        if not LOG_BLACKLIST:
            return super().filter(record)

        try:
            matches = self.regex.findall(record.msg)
            for match in matches:
                record.msg = self.replace(record.msg, match)

            args = []
            for arg in record.args:
                try:
                    arg_str = str(arg)
                    matches = self.regex.findall(arg_str)
                    if matches:
                        for match in matches:
                            arg_str = self.replace(arg_str, match)
                        arg = arg_str
                except Exception:
                    pass
                args.append(arg)
            record.args = tuple(args)
        except Exception:
            pass

        return super().filter(record)

    def replace(self, text, _match):
        return text


class PublicIPFilter(RegexFilter):
    """
    Log filter for public IP addresses.

    Class responsible for filtering public IP addresses.

    Attributes
    ----------
    regex : re.compile
        The compiled regex pattern.

    Methods
    -------
    replace:
        Filter that replaces a string within another string.

    Examples
    --------
    >>> PublicIPFilter()
    <common.logger.PublicIPFilter object at 0x...>
    """

    def __init__(self):
        super(PublicIPFilter, self).__init__()

        # Currently only checking for ipv4 addresses
        self.regex = re.compile(pattern=r'\d+(?:[.-]\d+){3}(?!\d*-[a-z0-9]{6})')

    def replace(self, text: str, ip: str) -> str:
        """
        Filter a public address.

        Filter the given ip address out of the given text. The ip address will only be filter if it is public.

        Parameters
        ----------
        text : str
            The text to replace the ip address within.
        ip : str
            The ip address to replace with asterisks.

        Returns
        -------
        str
            The original text with the ip address replaced.

        Examples
        --------
        >>> PublicIPFilter().replace(text='Testing 172.1.7.5', ip='172.1.7.5')
        'Testing ***.***.***.***'
        """
        if helpers.is_public_ip(ip.replace('-', '.')):
            partition = '-' if '-' in ip else '.'
            return text.replace(ip, partition.join(['***'] * 4))
        return text


class EmailFilter(RegexFilter):
    """
    Log filter for email addresses.

    Class responsible for filtering email addresses.

    Attributes
    ----------
    regex : re.compile
        The compiled regex pattern.

    Methods
    -------
    replace:
        Filter that replaces a string within another string.

    Examples
    --------
    >>> EmailFilter()
    <common.logger.EmailFilter object at 0x...>
    """

    def __init__(self):
        super(EmailFilter, self).__init__()

        self.regex = re.compile(pattern=r'([a-z0-9!#$%&\'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&\'*+/=?^_`{|}~-]+)*@'
                                r'(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)',
                                flags=re.IGNORECASE)

    def replace(self, text: str, email: str) -> str:
        """
        Filter an email address.

        Filter the given email address out of the given text.

        Parameters
        ----------
        text : str
            The text to replace the email address within.
        email : str
            The email address to replace with asterisks.

        Returns
        -------
        str
            The original text with the email address replaced.

        Examples
        --------
        >>> EmailFilter().replace(text='Testing example@example.com', email='example@example.com')
        'Testing ****************@********'
        """
        email_parts = email.partition('@')
        return text.replace(email, 16 * '*' + email_parts[1] + 8 * '*')


class PlexTokenFilter(RegexFilter):
    """
    Log filter for X-Plex-Token.

    Class responsible for filtering Plex tokens.

    Attributes
    ----------
    regex : re.compile
        The compiled regex pattern.

    Methods
    -------
    replace:
        Filter that replaces a string within another string.

    Examples
    --------
    >>> PlexTokenFilter()
    <common.logger.PlexTokenFilter object at 0x...>
    """

    def __init__(self):
        super(PlexTokenFilter, self).__init__()

        self.regex = re.compile(pattern=r'X-Plex-Token(?:=|%3D|:\s*)([a-zA-Z0-9_-]+)', flags=re.IGNORECASE)

    def replace(self, text: str, token: str) -> str:
        """
        Filter a token.

        Filter the given token out of the given text.

        Parameters
        ----------
        text : str
            The text to replace the token within.
        token : str
            The token to replace with asterisks.

        Returns
        -------
        str
            The original text with the token replaced.

        Examples
        --------
        >>> PlexTokenFilter().replace(text='x-plex-token=5FBCvHo9vFf9erz8ssLQ', token='5FBCvHo9vFf9erz8ssLQ')
        'x-plex-token=****************'
        """
        return text.replace(token, 16 * '*')


@contextlib.contextmanager
def listener(logger: logging.Logger):
    """
    Create a QueueListener.

    Wrapper that creates a QueueListener, starts it and automatically stops it.
    To be used in a with statement in the main process, for multiprocessing.

    Parameters
    ----------
    logger : logging.Logger
        The logger object.

    Yields
    ------
    None

    Examples
    --------
    >>> logger = get_logger(name='themerr-plex')
    >>> listener(logger=logger)
    """

    global queue

    # Initialize queue if not already done
    if queue is None:
        try:
            queue = multiprocessing.Queue()
        except OSError as e:
            queue = False

            # Some machines don't have access to /dev/shm. See
            # http://stackoverflow.com/questions/2009278 for more information.
            if e.errno == errno.EACCES:
                logger.warning('Multiprocess logging disabled, because current user cannot map shared memory. You '
                               'won\'t see any logging generated by the worker processed.')

    # Multiprocess logging may be disabled.
    if not queue:
        yield
    else:
        queue_listener = QueueListener(queue, *logger.handlers)

        try:
            queue_listener.start()
            yield
        finally:
            queue_listener.stop()


def init_multiprocessing(logger: logging.Logger):
    """
    Remove all handlers and add QueueHandler on top.

    This should only be called inside a multiprocessing worker process, since it changes the logger completely.

    Parameters
    ----------
    logger : logging.Logger
        The logger to initialize for multiprocessing.

    Examples
    --------
    >>> logger = get_logger(name='themerr-plex')
    >>> init_multiprocessing(logger=logger)
    """

    # Multiprocess logging may be disabled.
    if not queue:
        return

    # Remove all handlers and add the Queue handler as the only one.
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    queue_handler = QueueHandler(queue)
    queue_handler.setLevel(logging.DEBUG)

    logger.addHandler(queue_handler)

    # Change current thread name for log record
    threading.current_thread().name = multiprocessing.current_process().name


def get_logger(name: str) -> logging.Logger:  # this also exists in helpers.py to prevent circular imports
    """
    Get a logger.

    Application modules share ``themerr``. External logger names are preserved for library integration.
    Additionally, replace logger.warn with logger.warning.

    Parameters
    ----------
    name : str
        The name of the logger to get.

    Returns
    -------
    logging.Logger
        The logging.Logger object.

    Examples
    --------
    >>> get_logger(name='themerr-plex')
    <Logger themerr-plex (WARNING)>
    """
    logger = helpers.get_logger(name)
    logger.warn = logger.warning  # replace warn with warning

    return logger


def setup_loggers():
    """
    Setup all loggers.

    Setup all the available loggers.

    Examples
    --------
    >>> setup_loggers()
    """
    global _session_handler
    if _session_handler is None or _session_handler._closed:
        from common.log_viewer import _SessionLogHandler
        try:
            _session_handler = _SessionLogHandler()
        except OSError:
            _session_handler = None

    for logger_name in LOG_NAMES:
        init_logger(log_name=logger_name)
        if _session_handler is not None:
            logging.getLogger(logger_name).addHandler(_session_handler)

    # Libraries retain their native logger names and share the three output channels.
    for name, destination in (('uvicorn', 'backend'), ('schedule', 'themerr')):
        target = logging.getLogger(name)
        _remove_handlers(target)
        target.handlers = logging.getLogger(destination).handlers[:]
        target.setLevel(logging.getLogger(destination).level)
        target.propagate = False
    for name in ('uvicorn.error', 'uvicorn.access'):
        target = logging.getLogger(name)
        _remove_handlers(target)
        target.setLevel(logging.NOTSET)
        target.propagate = True
    access_logger = logging.getLogger('uvicorn.access')
    if not any(isinstance(value, LogPollFilter) for value in access_logger.filters):
        access_logger.filters.insert(0, LogPollFilter())


def _remove_handlers(target: logging.Logger):
    """Detach and close each old handler before rebuilding a logging channel."""
    for handler in target.handlers[:]:
        target.removeHandler(handler)
        if handler is not _session_handler:
            handler.close()


def redact(text: str) -> str:
    """Mask configured secrets and private values.

    Apply the configured secret blacklist and the public IP, email, and Plex token
    filters to the complete text, including any formatted traceback.

    Parameters
    ----------
    text : str
        Message or formatted log record to sanitize.

    Returns
    -------
    str
        Text with matching sensitive values replaced by asterisks.

    Examples
    --------
    >>> redact('X-Plex-Token=example_token')
    'X-Plex-Token=****************'
    """
    for word in _BLACKLIST_WORDS:
        text = text.replace(word, 16 * '*')
    for log_filter in (PublicIPFilter(), EmailFilter(), PlexTokenFilter()):
        for match in log_filter.regex.findall(text):
            text = log_filter.replace(text, match)
    return text


class PrivateFormatter(logging.Formatter):
    """Apply privacy filters to complete log records.

    Format the message, arguments, and exception before masking sensitive values.
    Accept the same formatting options as ``logging.Formatter``.

    Parameters
    ----------
    fmt : str or None, optional
        Record format, defaulting to the message alone.
    datefmt : str or None, optional
        Timestamp format, defaulting to the standard logging format.
    style : str, optional
        Format style: ``%``, ``{``, or ``$``. Defaults to ``%``.
    validate : bool, optional
        Validate the format against its style. Defaults to True.
    defaults : dict or None, optional
        Default values for custom record fields.

    Examples
    --------
    >>> formatter = PrivateFormatter('%(message)s')
    >>> record = logging.makeLogRecord({'msg': 'X-Plex-Token=example_token'})
    >>> formatter.format(record)
    'X-Plex-Token=****************'
    """

    def format(self, record):
        """Return a fully formatted, masked log record.

        Include interpolated arguments and exception details in the privacy pass.

        Parameters
        ----------
        record : logging.LogRecord
            Record containing the message and optional exception details.

        Returns
        -------
        str
            Formatted record with matching sensitive values masked.

        Examples
        --------
        >>> record = logging.makeLogRecord({'msg': 'Ready'})
        >>> PrivateFormatter('%(message)s').format(record)
        'Ready'
        """
        return redact(super().format(record))


class LogPollFilter(logging.Filter):
    """Suppress successful log viewer access records.

    Prevent live refresh requests from creating an endless stream of their own
    access messages. Retain failed polls and requests to other routes.

    Parameters
    ----------
    name : str, optional
        Inherited logging filter name, defaulting to an empty string. Poll
        suppression checks the request arguments regardless of this name.

    Examples
    --------
    >>> poll_filter = LogPollFilter()
    >>> record = logging.makeLogRecord({'msg': 'Server started', 'args': ()})
    >>> poll_filter.filter(record)
    True
    """

    def filter(self, record):
        """Retain failed polls and other Uvicorn access records.

        Suppress only successful GET requests to ``/api/logs``, including requests
        with query parameters. Other records remain available for diagnostics.

        Parameters
        ----------
        record : logging.LogRecord
            Uvicorn access record containing its request arguments.

        Returns
        -------
        bool
            False for a successful viewer poll, otherwise True.

        Examples
        --------
        >>> record = logging.makeLogRecord({'args': ('localhost', 'GET', '/api/logs', '1.1', 200)})
        >>> LogPollFilter().filter(record)
        False
        """
        args = record.args
        return not (isinstance(args, tuple) and len(args) == 5 and args[1] == 'GET'
                    and str(args[2]).partition('?')[0] == '/api/logs' and args[4] == 200)


class YtDlpLogger:
    """Route yt-dlp diagnostics to its logging channel.

    Implement yt-dlp's logger interface with the shared ``yt-dlp`` logger. Preserve
    normal progress messages as INFO and messages prefixed with ``[debug]`` as DEBUG.

    Examples
    --------
    >>> extractor_logger = YtDlpLogger()
    >>> options = {'logger': extractor_logger}
    """

    def debug(self, message):
        """Record an informational or debug extractor message.

        Distinguish DEBUG messages by yt-dlp's ``[debug]`` prefix followed by a space. Send other
        messages to INFO so download progress remains visible without debug logging.

        Parameters
        ----------
        message : str
            Diagnostic text supplied by yt-dlp.

        Examples
        --------
        >>> YtDlpLogger().debug('[download] Audio download complete')
        """
        target = get_logger('yt-dlp')
        if message.startswith('[debug] '):
            target.debug(message, stacklevel=2)
        else:
            target.info(message, stacklevel=2)

    def warning(self, message):
        """Record an extractor warning.

        Send the diagnostic to the ``yt-dlp`` channel at WARNING severity.

        Parameters
        ----------
        message : str
            Warning text supplied by yt-dlp.

        Examples
        --------
        >>> YtDlpLogger().warning('Retrying extraction after a timeout')
        """
        get_logger('yt-dlp').warning(message, stacklevel=2)

    def error(self, message):
        """Record an extractor failure.

        Send the diagnostic to the ``yt-dlp`` channel at ERROR severity.

        Parameters
        ----------
        message : str
            Failure text supplied by yt-dlp.

        Examples
        --------
        >>> YtDlpLogger().error('The source video is unavailable')
        """
        get_logger('yt-dlp').error(message, stacklevel=2)


def init_logger(log_name: str) -> logging.Logger:
    """
    Create a logger.

    Creates a logging.Logger object from the given log name.

    Parameters
    ----------
    log_name : str
        The name of the log to create.

    Returns
    -------
    logging.Logger
        The logging.Logger object.

    Examples
    --------
    >>> init_logger(log_name='themerr-plex')
    <Logger themerr-plex (INFO)>
    """
    logger = logging.getLogger(name=log_name)

    # Close and remove old handlers. This is required to reinitialize the loggers at runtime
    _remove_handlers(logger)

    # Configure the logger to accept all messages
    logger.propagate = False
    logger.setLevel(logging.DEBUG if common.DEBUG else logging.INFO)

    # Setup file logger
    formatter_class = logging.Formatter if common.DEV else PrivateFormatter
    file_formatter = formatter_class(
        '%(asctime)s.%(msecs)03d - %(levelname)-7s :: %(threadName)s : %(module)s : %(message)s',
        '%Y-%m-%d %H:%M:%S',
    )

    # Setup file logger
    log_dir = definitions.Paths.LOG_DIR
    if os.path.isdir(log_dir):
        filename = os.path.join(log_dir, f'{log_name}.log')
        file_handler = handlers.RotatingFileHandler(filename=filename, maxBytes=MAX_SIZE, backupCount=MAX_FILES,
                                                    encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(file_formatter)

        logger.addHandler(file_handler)

    # Setup console logger
    if not common.QUIET:
        console_formatter = file_formatter
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(logging.DEBUG)

        logger.addHandler(console_handler)

    # Install exception hooks
    if log_name == app_name:  # all uncaught tracebacks go to 'themerr.log'
        _init_hooks(logger)

    return logger


def _init_hooks(logger: logging.Logger, global_exceptions: bool = True, thread_exceptions: bool = True,
                pass_original: bool = True):
    """This method installs exception catching mechanisms.

    Any exception caught will pass through the exception hook, and will be logged to the logger as an error.
    Additionally, a traceback is provided.

    This is very useful for crashing threads and any other bugs, that may not be exposed when running as daemon.

    The default exception hook is still considered, if pass_original is True.
    """

    def excepthook(*exception_info):
        # We should always catch this to prevent loops!
        try:
            message = "".join(traceback.format_exception(*exception_info))
            logger.error("Uncaught exception: %s", message)
        except Exception:
            pass

        # Original excepthook
        if pass_original:
            sys.__excepthook__(*exception_info)

    # Global exception hook
    if global_exceptions:
        sys.excepthook = excepthook

    # Thread exception hook
    if thread_exceptions:
        old_init = threading.Thread.__init__

        def new_init(self, *args, **kwargs):
            old_init(self, *args, **kwargs)
            old_run = self.run

            def new_run(*args, **kwargs):
                try:
                    old_run(*args, **kwargs)
                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception:
                    excepthook(*sys.exc_info())

            self.run = new_run

        # Monkey patch the run() by monkey patching the __init__ method
        threading.Thread.__init__ = new_init


def shutdown():
    """
    Stop logging.

    Shutdown logging.

    Examples
    --------
    >>> shutdown()
    """
    logging.shutdown()


# get logger
log = get_logger(name=__name__)
