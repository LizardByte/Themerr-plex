# standard imports
import threading
import time
from typing import Any, Callable, Iterable, Mapping

# lib imports
import schedule

# local imports
from common import config
from common import logger
from plex.plexapi import scheduled_update
from themerr.cache import cache_data

log = logger.get_logger(name=__name__)


def run_threaded(
        target: Callable,
        daemon: bool = True,
        args: Iterable = (),
        task_name: str | None = None,
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
    daemon : bool, default True
        Whether the thread should be a daemon thread. Scheduled work must not keep a stopped process alive.
    args : Iterable
        The positional arguments to pass to the function.
    task_name : str or None, optional
        Human-readable scheduled job name to log at start and finish.
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
    def run_job() -> None:
        started = time.monotonic()
        log.info('Scheduled task started: %s', task_name)
        try:
            target(*args, **kwargs)
        except Exception:
            log.exception('Scheduled task failed: %s (%.1f seconds)', task_name, time.monotonic() - started)
        else:
            log.info('Scheduled task finished: %s (%.1f seconds)', task_name, time.monotonic() - started)

    job_thread = threading.Thread(target=run_job if task_name else target,
                                  args=() if task_name else args, kwargs={} if task_name else kwargs)
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
    log.info('Scheduler started; initial jobs will run in 60 seconds')
    time.sleep(60)  # give a little time for the server to start
    log.info('Dispatching initial scheduled jobs')
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
            target=scheduled_update,
            daemon=True,
            task_name='Theme scan and queue',
        )

    schedule.every(max(15, int(config.CONFIG['Themerr']['INT_UPDATE_DATABASE_CACHE_INTERVAL']))).minutes.do(
        job_func=run_threaded,
        target=cache_data,
        daemon=True,
        task_name='Dashboard refresh',
    )

    run_threaded(target=schedule_loop, daemon=True)  # start the schedule loop in a thread
