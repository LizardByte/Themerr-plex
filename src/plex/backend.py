"""Plex implementation of the media-server contracts."""

# standard imports
import re
from typing import Callable, Mapping
from urllib.parse import quote, urlencode

# lib imports
from plexapi import exceptions
from requests import Response

# local imports
from common import config, logger
from media_servers.base import MediaServer, MediaServerBackend, MediaServerError
from plex import auth, dashboard, plexapi, servers, tmdb, token_store
from themerr import storage

log = logger.get_logger(__name__)


class PlexMediaServer(MediaServer):
    """Keep native Plex operations within one server's storage scope.

    Parameters
    ----------
    server_id : str
        Plex machine identifier, or the legacy default scope.
    """

    def libraries(self) -> list[dict] | None:
        with storage.server_scope(self.server_id):
            connection = plexapi.setup_plexapi()
            if connection is None:
                return None
            return [
                {
                    'id': str(section.key),
                    'title': section.title,
                }
                for section in connection.library.sections()
            ]

    def cache_dashboard(self) -> bool:
        with storage.server_scope(self.server_id):
            return dashboard._cache_server()

    def scan(self, enqueue: Callable[[str], bool]) -> None:
        with storage.server_scope(self.server_id):
            plexapi.scan_items(enqueue)

    def update_item(self, item_id: str) -> bool:
        with storage.server_scope(self.server_id):
            return plexapi.update_plex_item(rating_key=int(item_id))

    def query_tmdb(self, path: str, params: dict) -> dict:
        with storage.server_scope(self.server_id):
            return tmdb.query(path, params)

    def web_urls(self, library_id: str, item_id: str | None = None) -> dict[str, str]:
        identifier = quote(self.server_id, safe='')
        server_url = f'https://app.plex.tv/desktop/#!/media/{identifier}/com.plexapp.plugins.library'
        urls = {
            'server': server_url,
            'library': f'{server_url}?{urlencode({"source": library_id})}',
        }
        if item_id is not None:
            item_query = urlencode({'key': f'/library/metadata/{item_id}'})
            urls['item'] = f'https://app.plex.tv/desktop/#!/server/{identifier}/details?{item_query}'
        return urls

    def open_poster(self, item_id: str) -> Response | None:
        if not str(item_id).isascii() or not str(item_id).isdigit():
            raise MediaServerError('Invalid Plex item identifier.', 404)
        try:
            with storage.server_scope(self.server_id):
                server = plexapi.setup_plexapi()
            if server is None:
                return None
            item = server.fetchItem(int(item_id))
            thumbnail = getattr(item, 'thumb', None)
            if not isinstance(thumbnail, str) or not re.fullmatch(r'/library/metadata/\d+/thumb(?:/\d+)?', thumbnail):
                return None
            return self._open_stream(server, thumbnail, {})
        except exceptions.NotFound:
            return None
        except (
            exceptions.PlexApiException,
            OSError,
            ValueError,
        ) as error:
            log.warning('Unable to load poster for item_id=%s (%s)', item_id, type(error).__name__)
            raise MediaServerError('Unable to load poster from Plex.', 502) from error

    def open_theme(self, item_id: str, headers: Mapping[str, str]) -> Response:
        if not str(item_id).isascii() or not str(item_id).isdigit():
            raise MediaServerError('Invalid Plex item identifier.', 404)
        try:
            with storage.server_scope(self.server_id):
                server = plexapi.setup_plexapi()
            if server is None:
                raise MediaServerError('Connect to Plex before playing themes.', 503)
            item = server.fetchItem(int(item_id))
            theme_path = getattr(item, 'theme', None)
            if not theme_path:
                raise MediaServerError('This item has no theme.', 404)
            if not theme_path.startswith('/library/metadata/') or '/theme/' not in theme_path:
                raise MediaServerError('Plex returned an unsupported theme path.', 502)
            return self._open_stream(server, theme_path, headers)
        except exceptions.NotFound as error:
            raise MediaServerError('This Plex item is no longer available.', 404) from error
        except (
            exceptions.PlexApiException,
            OSError,
            ValueError,
        ) as error:
            log.warning('Unable to load theme for item_id=%s (%s)', item_id, type(error).__name__)
            raise MediaServerError('Unable to load theme audio from Plex.', 502) from error

    @staticmethod
    def _open_stream(server, path: str, headers: Mapping[str, str]) -> Response:
        """Open a validated native Plex media path using backend-only credentials."""
        return server._session.get(
            server.url(path, includeToken=False),
            headers=server._headers(**headers),
            stream=True,
            allow_redirects=False,
            timeout=config.CONFIG['Themerr']['INT_PLEXAPI_PLEXAPI_TIMEOUT'],
        )


class PlexBackend(MediaServerBackend):
    """Manage Plex connections without changing persisted settings or credentials."""

    name = 'Plex'

    def server(self, server_id: str) -> MediaServer:
        return PlexMediaServer(server_id)

    def list_servers(self, enabled_only: bool = False) -> list[dict]:
        return servers.list_servers(enabled_only)

    def get_server(self, server_id: str) -> dict | None:
        return servers.get_server(server_id)

    def update_server(self, server_id: str, values: dict) -> None:
        servers.update_server(server_id, values)

    def remove_server(self, server_id: str) -> None:
        try:
            servers.remove_server(server_id)
        except token_store.TokenStorageError as error:
            raise MediaServerError('Could not update the secure credential store.', 500) from error

    def record_refresh(self, server_id: str, error: str | None = None) -> None:
        servers.record_refresh(server_id, error)

    def account_connected(self) -> bool:
        return bool(auth.get_token())

    def start_listeners(self) -> None:
        plexapi.plex_listener()

    def stop_listeners(self) -> None:
        plexapi.stop_plex_listener()

    def web_router(self):
        from plex.web import router

        return router
