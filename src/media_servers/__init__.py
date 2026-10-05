"""Select the installed media-server integration for shared application services."""

from functools import lru_cache

from media_servers.base import MediaServerBackend


@lru_cache(maxsize=1)
def get_backend() -> MediaServerBackend:
    """Return the application's media-server backend.

    Plex is the sole supported implementation. Keep that selection here so shared
    services do not import the integration or its SDK directly.

    Returns
    -------
    MediaServerBackend
        The Plex integration.

    Examples
    --------
    >>> get_backend().name
    'Plex'
    """
    from plex.backend import PlexBackend
    return PlexBackend()
