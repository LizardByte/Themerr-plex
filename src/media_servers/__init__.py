"""Dispatch shared services to independently scoped media-server integrations."""

from functools import lru_cache

from media_servers.base import MediaServerBackend


class ServerRegistry(MediaServerBackend):
    """Combine installed integrations while preserving existing Plex identifiers."""

    name = 'media server'

    def __init__(self):
        from plex.backend import PlexBackend
        from jellyfin.backend import JellyfinBackend
        self.plex = PlexBackend()
        self.jellyfin = JellyfinBackend()

    def _backend(self, server_id):
        return self.jellyfin if server_id.startswith('jellyfin:') else self.plex

    def server(self, server_id):
        return self._backend(server_id).server(server_id)

    def display_name(self, server_id):
        return self._backend(server_id).name

    def list_servers(self, enabled_only=False):
        return [{**record, 'type': kind} for kind, backend in (('plex', self.plex), ('jellyfin', self.jellyfin))
                for record in backend.list_servers(enabled_only)]

    def get_server(self, server_id):
        return self._backend(server_id).get_server(server_id)

    def update_server(self, server_id, values):
        self._backend(server_id).update_server(server_id, values)

    def remove_server(self, server_id):
        self._backend(server_id).remove_server(server_id)

    def record_refresh(self, server_id, error=None):
        self._backend(server_id).record_refresh(server_id, error)

    def account_connected(self):
        return self.plex.account_connected()

    def start_listeners(self):
        self.plex.start_listeners()
        self.jellyfin.start_listeners()

    def stop_listeners(self):
        self.plex.stop_listeners()
        self.jellyfin.stop_listeners()

    def web_router(self):
        from fastapi import APIRouter
        return APIRouter(routes=[*self.plex.web_router().routes, *self.jellyfin.web_router().routes])


@lru_cache(maxsize=1)
def get_backend() -> MediaServerBackend:
    """Return the application's media-server backend.

    Saved identities select Plex or Jellyfin without importing their native APIs
    into the shared dashboard, queue, or playback services.

    Returns
    -------
    MediaServerBackend
        Registry of installed integrations.

    Examples
    --------
    >>> get_backend().name
    'media server'
    """
    return ServerRegistry()
