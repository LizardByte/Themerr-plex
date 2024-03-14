# -*- coding: utf-8 -*-

# standard imports
import logging
import threading
import time

# plex debugging
try:
    import plexhints  # noqa: F401
except ImportError:
    pass
else:  # the code is running outside of Plex
    from plexhints.log_kit import Log  # log kit
    from plexhints.prefs_kit import Prefs  # prefs kit

# imports from Libraries\Shared
import schedule
from typing import Any, Callable, Iterable, Mapping, Optional

# local imports
from constants import plugin_identifier
from plex_api_helper import scheduled_update
from webapp import cache_data

# setup logging for schedule
Log.Info('Adding schedule log handlers to plex plugin logger')

# get the plugin logger
plugin_logger = logging.getLogger(plugin_identifier)

schedule.logger.handlers = plugin_logger.handlers
schedule.logger.setLevel(plugin_logger.level)

# test message
schedule.logger.info('schedule logger test message')


def run_threaded(target, daemon=None, args=(), **kwargs):
    # type: (Callable, Optional[bool], Iterable, Mapping[str, Any]) -> threading.Thread
    """
    Run a function in a thread.

    Allows to run a function in a thread, which is useful for long-running tasks, and it
    allows the main thread to continue.

    Parameters
    ----------
    target : Callable
        The function to run in a thread.
    daemon : Optional[py:class:`bool`]
        Whether the thread should be a daemon thread.
    args : Iterable
        The positional arguments to pass to the function.
    kwargs : Mapping[str, Any]
        The keyword arguments to pass to the function.

    Returns
    -------
    threading.Thread
        The thread that the function is running in.

    Examples
    --------
    >>> run_threaded(target=Log.Info, daemon=True, args=['Hello, world!'])
    "Hello, world!"
    """
    job_thread = threading.Thread(target=target, args=args, kwargs=kwargs)
    if daemon:
        job_thread.daemon = True
    job_thread.start()
    return job_thread


def schedule_loop():
    # type: () -> None
    """
    Start the schedule loop.

    Before the schedule loop is started, all jobs are run once.

    Examples
    --------
    >>> schedule_loop()
    ...
    """
    time.sleep(60)  # give a little time for the server to start
    schedule.run_all()  # run all jobs once

    while True:
        schedule.run_pending()
        time.sleep(1)


def setup_scheduling():
    # type: () -> None
    """
    Sets up the scheduled tasks.

    The Tasks setup depend on the preferences set by the user.

    Examples
    --------
    >>> setup_scheduling()
    ...

    See Also
    --------
    plex_api_helper.scheduled_update : Scheduled function to update the themes.
    """
    if Prefs['bool_auto_update_items']:
        schedule.every(max(15, int(Prefs['int_update_themes_interval']))).minutes.do(
            job_func=run_threaded,
            target=scheduled_update
        )

    schedule.every(max(15, int(Prefs['int_update_database_cache_interval']))).minutes.do(
        job_func=run_threaded,
        target=cache_data
    )

    run_threaded(target=schedule_loop, daemon=True)  # start the schedule loop in a thread
