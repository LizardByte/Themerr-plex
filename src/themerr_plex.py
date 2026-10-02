#!/usr/bin/env python3
"""
Themerr-plex.py

Responsible for starting Themerr Plex.
"""
# standard imports
import argparse
import getpass
import os
import sys
import time

# local imports
import common
from common import config
from common import definitions
from common import helpers
from common import locales
from common import logger
from common import threads

app_name = definitions.Names.name.lower()

# locales
_ = locales.get_text()

# get logger
log = logger.get_logger(name=app_name)


class IntRange(object):
    """
    Custom IntRange class for argparse.

    Prevents printing out large list of possible choices for integer ranges.

    Parameters
    ----------
    stop : int
        Range maximum value.
    start : int, default = 0
        Range minimum value.

    Methods
    -------
    __call__:
        Validate that value is within accepted range.

    Examples
    --------
    >>> IntRange(0, 10)
    <themerr-plex.IntRange object at 0x...>
    """
    def __init__(self, stop: int, start: int = 0,):
        """
        Initialize the IntRange class object.

        If stop is less than start, the values will be corrected automatically.
        """
        if stop < start:
            stop, start = start, stop
        self.start, self.stop = start, stop

    def __call__(self, value: int | str) -> int:
        """
        Validate that value is within accepted range.

        Validate the provided value is within the range of the `IntRange()` object.

        Parameters
        ----------
        value : Union[int, str]
            The value to validate.

        Returns
        -------
        int
            The original value.

        Raises
        ------
        argparse.ArgumentTypeError
            If provided value is outside the accepted range.

        Examples
        --------
        >>> IntRange(0, 10).__call__(5)
        5

        >>> IntRange(0, 10).__call__(15)
        Traceback (most recent call last):
            ...
        argparse.ArgumentTypeError: Value outside of range: (0, 10)
        """
        value = int(value)
        if value < self.start or value >= self.stop:
            raise argparse.ArgumentTypeError(f'Value outside of range: ({self.start}, {self.stop})')
        return value


def _apply_cli_options(args: argparse.Namespace) -> None:
    """Initialize configuration and logging from parsed CLI options.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed command line arguments.
    """
    config_file = args.config or os.path.join(definitions.Paths.CONFIG_DIR, definitions.Files.CONFIG)
    if args.debug:
        common.DEBUG = True
    if args.dev:
        common.DEV = True
    if args.quiet:
        common.QUIET = True

    # Submodules using translations are imported only after initialization.
    common.initialize(config_file=config_file)

    if args.config:
        log.info(f'{definitions.Names.name} is using custom config file: {config_file}.')
    if args.debug:
        log.info(f'{definitions.Names.name} will log debug messages.')
    if args.dev:
        log.info(f'{definitions.Names.name} is running in the dev environment.')
    if args.quiet:
        log.info(f'{definitions.Names.name} is running in quiet mode. Nothing will be printed to console.')

    if args.port:
        config.CONFIG['Network']['HTTP_PORT'] = args.port
        config.CONFIG.write()


def main():
    """
    Application entry point.

    Parses arguments and initializes the application.

    Examples
    --------
    >>> if __name__ == "__main__":
    ...     main()
    """
    # Fixed paths
    splash = None
    if definitions.Modes.FROZEN and definitions.Modes.SPLASH:
        try:
            import pyi_splash  # module cannot be installed outside of pyinstaller builds
            pyi_splash.update_text(f'Attempting to start {definitions.Names.name}')
        except (ImportError, RuntimeError):
            pass  # the splash may be unavailable on headless machines
        else:
            splash = pyi_splash

    # Set up and gather command line arguments
    parser = argparse.ArgumentParser(description=_('%(app_name)s manages theme songs for Plex.\n'
                                                   'Arguments supplied here are meant to be temporary.')
                                     % {'app_name': definitions.Names.name},
                                     add_help=False)
    parser.add_argument('-h', '--help', action='help', help=_('Show this help message and exit'))

    parser.add_argument('--config', help=_('Specify a config file to use'))
    parser.add_argument('--debug', action='store_true', help=_('Use debug logging level'))
    parser.add_argument('--dev', action='store_true', help=_('Start %(app_name)s in the development environment')
                        % {'app_name': definitions.Names.name})
    parser.add_argument('--docker_healthcheck', action='store_true', help=_('Health check the container and exit'))
    parser.add_argument('--reset-admin-password', action='store_true',
                        help='Reset the application admin password from this console')
    parser.add_argument('--nolaunch', action='store_true', help=_('Do not open %(app_name)s in browser')
                        % {'app_name': definitions.Names.name})
    parser.add_argument('-p', '--port', default=9494, type=IntRange(21, 65535),
                        help=_('Force %(app_name)s to run on a specified port, default=9494')
                        % {'app_name': definitions.Names.name}
                        )
    parser.add_argument('-q', '--quiet', action='store_true', help=_('Turn off console logging'))
    parser.add_argument('-v', '--version', action='store_true', help=_('Print the version details and exit'))

    args = parser.parse_args()

    if args.docker_healthcheck:
        status = helpers.docker_healthcheck()
        exit_code = int(not status)
        sys.exit(exit_code)

    if args.version:
        print('version arg is not yet implemented')
        sys.exit()

    _apply_cli_options(args)

    from themerr import storage
    storage.engine()
    from common import admin
    if args.reset_admin_password:
        password = getpass.getpass('New admin password (at least 12 characters): ')
        if password != getpass.getpass('Confirm password: '):
            parser.error('The passwords do not match.')
        try:
            admin.reset_password(password)
        except ValueError as exc:
            parser.error(str(exc))
        print('Admin password reset. Existing sessions have been invalidated.')
        return

    if config.CONFIG['General']['SYSTEM_TRAY']:
        from common import tray_icon  # submodule requires translations so importing after initialization
        # also do not import if not required by config options

        tray_icon.tray_run_threaded()

    # start the webapp
    if splash is not None:
        splash.update_text("Starting the webapp")
        time.sleep(3)  # show splash screen for a min of 3 seconds
        splash.close()  # close the splash screen
    from common import webapp  # import at use due to translations
    from plex import plexapi  # import at use due to config
    from themerr import scheduled_tasks

    scheme = 'https' if config.CONFIG['Network']['SSL'] else 'http'
    browser_url = admin.startup_url(f"{scheme}://127.0.0.1:{config.CONFIG['Network']['HTTP_PORT']}")
    if not admin.account():
        print(f'Create your Themerr admin account using this one-time link: {browser_url}', flush=True)

    threads.run_in_thread(target=webapp.start_webapp, name='Flask', daemon=True).start()

    # this should be after starting flask app
    if config.CONFIG['General']['LAUNCH_BROWSER'] and not args.nolaunch:
        helpers.open_url_in_browser(url=browser_url)

    # start plex listener
    plexapi.start_queue_threads()
    plexapi.plex_listener()

    # scheduled tasks
    scheduled_tasks.setup_scheduling()

    wait()  # wait for signal


def wait():
    """
    Wait for signal.

    Endlessly loop while `common.SIGNAL = None`.
    If `common.SIGNAL` is changed to `shutdown` or `restart` `common.stop()` will be executed.
    If KeyboardInterrupt signal is detected `common.stop()` will be executed.

    Examples
    --------
    >>> wait()
    """
    log.info(f'{definitions.Names.name} is ready!')

    while True:  # wait endlessly for a signal
        if not common.SIGNAL:
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                common.SIGNAL = 'shutdown'
        else:
            log.info(f'Received signal: {common.SIGNAL}')

            if common.SIGNAL == 'shutdown':
                common.stop()
            elif common.SIGNAL == 'restart':
                common.stop(restart=True)
            else:
                log.error('Unknown signal. Shutting down...')
                common.stop()

            break


if __name__ == "__main__":
    main()
