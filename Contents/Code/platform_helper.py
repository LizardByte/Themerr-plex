# -*- coding: utf-8 -*-

# standard imports
import os
import platform

# plex debugging
try:
    import plexhints  # noqa: F401
except ImportError:
    pass
else:  # the code is running outside of Plex
    from plexhints.log_kit import Log  # log kit


def get_os_architecture():
    # type: () -> str
    """
    Get the OS architecture.

    Returns
    -------
    str
        The OS architecture. One of ``x86_64``, ``x86``, ``aarch64`` or ``Unknown architecture``.

    Examples
    --------
    >>> get_os_architecture()
    "x86_64"
    """
    # Getting architecture using platform module
    machine = platform.machine()

    # For more detailed check, especially for Windows OS
    if os.name == 'nt':
        # Possible values: '32bit', '64bit'
        # This will tell us if the OS is 64-bit or 32-bit
        architecture = platform.architecture()

        if architecture[0] == '64bit':
            return 'x86_64'
        elif architecture[0] == '32bit':
            return 'x86'
        else:
            return 'Unknown architecture'
    else:
        # For Unix/Linux systems, we can rely more on platform.machine()
        if machine in ['x86_64', 'AMD64']:
            return 'x86_64'
        elif machine in ['i386', 'i686', 'x86']:
            return 'x86'
        elif machine in ['aarch64', 'arm64']:
            return 'aarch64'
        else:
            return 'Unknown architecture'


# constants
architecture = get_os_architecture()
os_system = platform.system().lower()
