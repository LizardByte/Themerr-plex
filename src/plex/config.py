"""Lifecycle callbacks for compatible Plex configuration keys."""

# local imports
from common import logger
from plex import plexapi

log = logger.get_logger(__name__)


def reconnect() -> None:
    """Reconnect after the configured legacy Plex URL changes."""
    plexapi.stop_plex_listener()
    plexapi.plex_server = None
    if plexapi.auth.get_token():
        try:
            plexapi.plex_listener()
        except Exception:
            log.exception('Unable to reconnect to the changed Plex URL')
