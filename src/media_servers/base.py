"""Contracts between media-server integrations and Themerr's shared services."""

from abc import ABC, abstractmethod
from typing import Callable, Mapping

from fastapi import APIRouter
from requests import Response


class MediaServerError(Exception):
    """An integration failure safe to report to an authenticated client.

    Adapters translate native SDK failures into fixed messages and HTTP statuses.
    Callers can expose this exception without serializing the original cause.

    Parameters
    ----------
    message : str
        Fixed public explanation without upstream credentials or response bodies.
    status_code : int
        HTTP status for the public failure.

    Examples
    --------
    >>> error = MediaServerError('This item has no theme.', 404)
    >>> error.status_code
    404
    """

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


class MediaServer(ABC):
    """Operations on one server, using opaque item and library identifiers.

    Implementations own native SDK objects, credentials, protocol paths, metadata
    interpretation, and upload handling. Shared callers receive dashboard data or
    an HTTP stream, never native SDK objects. Each operation must retain the
    server's storage scope, including when invoked by a background worker.

    Parameters
    ----------
    server_id : str
        Saved server identifier, or the legacy default connection identifier.
    """

    def __init__(self, server_id: str):
        self.server_id = server_id

    @abstractmethod
    def libraries(self) -> list[dict] | None:
        """Return library choices, or None when a live connection is unavailable.

        Returns
        -------
        list of dict or None
            Library dictionaries with string ``id`` and ``title`` fields.
        """

    @abstractmethod
    def cache_dashboard(self) -> bool:
        """Publish a complete dashboard snapshot in this server's storage scope.

        Returns
        -------
        bool
            Whether a complete snapshot was published.
        """

    @abstractmethod
    def scan(self, enqueue: Callable[[str], bool]) -> None:
        """Queue eligible items while honoring integration processing settings.

        Parameters
        ----------
        enqueue : callable
            Callback accepting an opaque item identifier in this server's scope.
        """

    @abstractmethod
    def update_item(self, item_id: str) -> bool:
        """Apply theme and metadata updates to an eligible item.

        Parameters
        ----------
        item_id : str
            Opaque server item identifier.

        Returns
        -------
        bool
            Whether the item was processed successfully.
        """

    @abstractmethod
    def open_poster(self, item_id: str) -> Response | None:
        """Open a credentialed poster stream without following redirects.

        Parameters
        ----------
        item_id : str
            Opaque server item identifier.

        Returns
        -------
        requests.Response or None
            Stream owned and closed by the caller, or no poster.
        """

    @abstractmethod
    def open_theme(self, item_id: str, headers: Mapping[str, str]) -> Response:
        """Open the selected theme stream without following redirects.

        Parameters
        ----------
        item_id : str
            Opaque server item identifier.
        headers : mapping of str to str
            Byte-range and encoding headers supplied by the playback service.

        Returns
        -------
        requests.Response
            Stream owned and closed by the caller.
        """

    @abstractmethod
    def web_urls(self, library_id: str, item_id: str | None = None) -> dict[str, str]:
        """Build browser links using the integration's native URL format.

        Parameters
        ----------
        library_id : str
            Library identifier.
        item_id : str or None, optional
            Item identifier when an item link is needed.

        Returns
        -------
        dict of str to str
            ``server``, ``library``, and optionally ``item`` URLs.
        """

    def query_tmdb(self, path: str, params: dict) -> dict:
        """Optionally resolve metadata through this server's TMDB service.

        Parameters
        ----------
        path : str
            TMDB service path.
        params : dict
            TMDB query parameters.

        Returns
        -------
        dict
            JSON data, or an empty dictionary when this capability is unavailable.
        """
        return {}


class MediaServerBackend(ABC):
    """Manage saved connections and the lifecycle of one integration.

    Attributes
    ----------
    name : str
        Display name used in public status messages.
    """

    name: str

    def display_name(self, server_id: str) -> str:
        """Return the integration name for public messages about one saved server.

        Parameters
        ----------
        server_id : str
            Saved server identity.

        Returns
        -------
        str
            Integration display name.
        """
        return self.name

    @abstractmethod
    def server(self, server_id: str) -> MediaServer:
        """Create an operations adapter for a saved or legacy default connection.

        Parameters
        ----------
        server_id : str
            Server identifier.

        Returns
        -------
        MediaServer
            Adapter retaining this identity throughout its operations.
        """

    @abstractmethod
    def list_servers(self, enabled_only: bool = False) -> list[dict]:
        """Read saved public connection settings without credentials.

        Parameters
        ----------
        enabled_only : bool, optional
            Include only connections enabled for processing.

        Returns
        -------
        list of dict
            Saved server settings including identity, name, and enabled state.
        """

    @abstractmethod
    def get_server(self, server_id: str) -> dict | None:
        """Find public settings for one saved connection.

        Parameters
        ----------
        server_id : str
            Server identifier.

        Returns
        -------
        dict or None
            Saved settings, or no matching server.
        """

    @abstractmethod
    def update_server(self, server_id: str, values: dict) -> None:
        """Validate and save processing preferences.

        Parameters
        ----------
        server_id : str
            Server identifier.
        values : dict
            Submitted preferences.
        """

    @abstractmethod
    def remove_server(self, server_id: str) -> None:
        """Remove a connection and its credentials and cached state.

        Parameters
        ----------
        server_id : str
            Server identifier.
        """

    @abstractmethod
    def record_refresh(self, server_id: str, error: str | None = None) -> None:
        """Record a successful refresh or a sanitized failure.

        Parameters
        ----------
        server_id : str
            Server identifier.
        error : str or None, optional
            Fixed public error, cleared on success.
        """

    @abstractmethod
    def account_connected(self) -> bool:
        """Report whether account authorization is available.

        Returns
        -------
        bool
            Whether account credentials are present.
        """

    @abstractmethod
    def start_listeners(self) -> None:
        """Replace event listeners for the currently enabled connections."""

    @abstractmethod
    def stop_listeners(self) -> None:
        """Stop the integration's event listeners."""

    @abstractmethod
    def web_router(self) -> APIRouter:
        """Expose integration-specific sign-in and discovery routes.

        Returns
        -------
        APIRouter
            Routes protected by the application's authentication and CSRF middleware.
        """
