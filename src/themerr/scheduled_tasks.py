# standard imports
import threading
import time

# lib imports
import schedule
from typing import Any, Callable, Iterable, Mapping, Optional

# local imports
from common import config
from common import logger
from plex.plexapi import scheduled_update
from themerr.cache import cache_data

log = logger.get_logger(name=__name__)

# setup logging for schedule
log.info('Adding schedule log handlers to plex plugin logger')

schedule.logger.handlers = log.handlers
schedule.logger.setLevel(log.level)

# test message
schedule.logger.info('schedule logger test message')


def run_threaded(
        target: Callable,
        daemon: Optional[bool] = None,
        args: Iterable = (),
        **kwargs: Mapping[str, Any],
) -> threading.Thread:
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
    >>> run_threaded(target=log.info, daemon=True, args=['Hello, world!'])
    "Hello, world!"
    """
    job_thread = threading.Thread(target=target, args=args, kwargs=kwargs)
    if daemon:
        job_thread.daemon = True
    job_thread.start()
    return job_thread


def schedule_loop() -> None:
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


def setup_scheduling() -> None:
    """
    Sets up the scheduled tasks.

    The Tasks setup depends on the preferences set by the user.

    Examples
    --------
    >>> setup_scheduling()
    ...

    See Also
    --------
    plex_api_helper.scheduled_update : Scheduled function to update the themes.
    """
    if config.CONFIG['Themerr']['BOOL_THEMERR_ENABLED']:
        schedule.every(max(15, int(config.CONFIG['Themerr']['INT_UPDATE_THEMES_INTERVAL']))).minutes.do(
            job_func=run_threaded,
            target=scheduled_update
        )

    schedule.every(max(15, int(config.CONFIG['Themerr']['INT_UPDATE_DATABASE_CACHE_INTERVAL']))).minutes.do(
        job_func=run_threaded,
        target=cache_data
    )

    run_threaded(target=schedule_loop, daemon=True)  # start the schedule loop in a thread
