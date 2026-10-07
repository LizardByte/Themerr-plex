"""Discover, connect, and persist independently scoped Plex servers."""

# standard imports
from datetime import datetime, timezone
from threading import RLock
from urllib.parse import urlsplit

# lib imports
from plexapi.gdm import GDM
from plexapi.myplex import MyPlexAccount
from sqlalchemy import Boolean, String, delete, select
from sqlalchemy.orm import Mapped, Session, mapped_column

# local imports
from common import logger
from common.validation import ValidationError, ValidationMessage
from plex import auth, token_store
from themerr import storage

log = logger.get_logger(__name__)
_lock = RLock()
_connections = {}


def credential_id(server_id: str) -> str:
    """Namespace server credentials by installation as well as machine identifier.

    Parameters
    ----------
    server_id : str
        Plex machine identifier.

    Returns
    -------
    str
        Unique credential-store key for this installation's server.
    """
    return 'server:' + auth._client_identifier() + ':' + server_id


class ServerRecord(storage.Base):
    """Connection settings without Plex credentials."""

    __tablename__ = 'plex_servers'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[str | None] = mapped_column(String)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    data_directory: Mapped[str] = mapped_column(String, nullable=False, default='')
    ignored_libraries: Mapped[str] = mapped_column(String, nullable=False, default='')
    last_refresh: Mapped[str | None] = mapped_column(String)
    last_error: Mapped[str | None] = mapped_column(String)


def list_servers(enabled_only: bool = False) -> list[dict]:
    """Return saved server settings.

    Parameters
    ----------
    enabled_only : bool, optional
        Include only servers enabled for processing.

    Returns
    -------
    list of dict
        Public connection settings, without credentials.
    """
    with Session(storage.engine()) as session:
        query = select(ServerRecord).order_by(ServerRecord.name)
        if enabled_only:
            query = query.where(ServerRecord.enabled.is_(True))
        return [{column.name: getattr(row, column.name) for column in ServerRecord.__table__.columns}
                for row in session.scalars(query)]


def get_server(server_id: str) -> dict | None:
    """Find saved settings for a machine identifier.

    Parameters
    ----------
    server_id : str
        Plex machine identifier.

    Returns
    -------
    dict or None
        Public server settings.
    """
    return next((row for row in list_servers() if row['id'] == server_id), None)


def account_resources() -> list:
    """Read servers accessible to the paired Plex account.

    Returns
    -------
    list
        Plex resources; their tokens must stay on the backend.
    """
    token = auth.get_token()
    if not token:
        raise ValueError('Connect your Plex account first.')
    return [resource for resource in MyPlexAccount(token=token, timeout=10).resources()
            if 'server' in resource.provides]


def discover_account() -> list[dict]:
    """List account servers and their advertised addresses.

    Returns
    -------
    list of dict
        Safe resource metadata for server selection.
    """
    log.info('Finding servers advertised by the linked Plex account')
    found = [{'id': resource.clientIdentifier, 'name': resource.name, 'owned': resource.owned,
              'connections': [{'url': connection.uri, 'local': connection.local,
                               'relay': connection.relay} for connection in resource.connections]}
             for resource in account_resources()]
    log.info('Plex account discovery finished: %d servers advertised; addresses have not been tested', len(found))
    return found


def discover_local() -> list[dict]:
    """Find nearby Plex servers with Plex's GDM multicast protocol.

    Returns
    -------
    list of dict
        Names and local addresses advertised by Plex.
    """
    log.info('Discovering Plex servers on LAN using GDM multicast')
    discovery = GDM()
    discovery.scan()
    found = []
    for entry in discovery.entries:
        data = entry['data']
        if data.get('Content-Type') != 'plex/media-server':
            continue
        host = entry['from'][0]
        try:
            port = int(data.get('Port', 32400))
        except (ValueError, TypeError):
            continue
        if 1 <= port <= 65535:
            # GDM advertises an IP and port; Plex's HTTPS certificate requires its account-provided plex.direct host.
            address = f'http://{host}:{port}'  # NOSONAR python:S5332: Preserve the advertised LAN HTTP connection.
            found.append({'id': data.get('Resource-Identifier'), 'name': data.get('Name', host),
                          'connections': [{'url': address, 'local': True, 'relay': False}]})
    log.info('Plex LAN discovery finished: %d servers responded', len(found))
    return found


def validate_url(url: str) -> str:
    """Validate a manually entered Plex address.

    Parameters
    ----------
    url : str
        HTTP or HTTPS base address.

    Returns
    -------
    str
        Normalized base URL.

    Raises
    ------
    ValidationError
        The address includes credentials or is not an HTTP base URL.
    """
    if not isinstance(url, str) or len(url) > 2048:
        raise ValidationError(ValidationMessage.PLEX_ADDRESS_INVALID)
    if '\\' in url or any(ord(character) < 32 for character in url):
        raise ValidationError(ValidationMessage.PLEX_ADDRESS_CHARACTERS)
    try:
        parts = urlsplit(url.strip())
    except ValueError as exc:
        raise ValidationError(ValidationMessage.PLEX_ADDRESS_INVALID) from exc
    if (parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password or
            parts.query or parts.fragment or parts.path not in ('', '/')):
        raise ValidationError(ValidationMessage.PLEX_BASE_ADDRESS_REQUIRED)
    try:
        port = parts.port
    except ValueError as exc:
        raise ValidationError(ValidationMessage.PLEX_PORT_INVALID) from exc
    if port is not None and not 1 <= port <= 65535:
        raise ValidationError(ValidationMessage.PLEX_PORT_INVALID)
    return url.strip().rstrip('/')


def _set_server_version(record, server):
    """Copy a valid version reported by an authenticated Plex connection."""
    version = getattr(server, 'version', None)
    if isinstance(version, str) and version:
        record.version = version[:64]


def add_server(url: str, resource_id: str | None = None) -> dict:
    """Verify an address, save its token securely, and register the server.

    Parameters
    ----------
    url : str
        Selected or manually supplied address.
    resource_id : str or None, optional
        Expected machine identifier of a discovered resource.

    Returns
    -------
    dict
        Saved server settings.

    Raises
    ------
    ValidationError
        The server is inaccessible or its identifier does not match.
    """
    from plex.plexapi import connect_plex_server

    url = validate_url(url)
    token = auth.get_token()
    if not token:
        raise ValidationError(ValidationMessage.PLEX_ACCOUNT_REQUIRED)
    # Shared servers use a resource access token, rather than the account token.
    try:
        resources = account_resources()
    except Exception:
        if resource_id:
            raise
        resources = []  # A manual connection can still use the securely saved account token.
    resource = next((item for item in resources if item.clientIdentifier == resource_id), None)
    if resource_id is None:
        resource = next((item for item in resources if any(
            connection.uri.rstrip('/') == url for connection in item.connections
        )), None)
    if resource_id and resource is None:
        raise ValidationError(ValidationMessage.PLEX_SERVER_UNAVAILABLE)
    token = resource.accessToken if resource else token
    logger.blacklist_config({'Plex': {'PLEX_TOKEN': token}})
    log.info('Connecting to Plex server at %s', url)
    server = connect_plex_server(url, token)
    server_id = server.machineIdentifier
    if not isinstance(server_id, str) or not server_id or server_id == 'default':
        raise ValidationError(ValidationMessage.PLEX_IDENTIFIER_INVALID)
    if resource_id and server_id != resource_id:
        raise ValidationError(ValidationMessage.PLEX_SERVER_MISMATCH)
    token_store.save_token(credential_id(server_id), token)
    logger.blacklist_config({'Plex': {'PLEX_TOKEN': token}})
    with _lock:
        with Session(storage.engine()) as session:
            record = session.get(ServerRecord, server_id)
            if record is None:
                record = ServerRecord(id=server_id, name=server.friendlyName, url=url)
                session.add(record)
            else:
                record.url = url
                record.name = server.friendlyName
                record.enabled = True
                record.last_error = None
            _set_server_version(record, server)
            session.commit()
        _connections[server_id] = server
    log.info('Connected and saved Plex server %s at %s', server.friendlyName, url)
    return get_server(server_id)


def connect(server_id: str):
    """Return a connection for an enabled registered server.

    Parameters
    ----------
    server_id : str
        Plex machine identifier.

    Returns
    -------
    PlexServer or None
        Verified connection, or no connection when paused or removed.
    """
    from plex.plexapi import connect_plex_server

    record = get_server(server_id)
    if record is None or not record['enabled']:
        return None
    with _lock:
        if server_id not in _connections:
            token = token_store.get_token(credential_id(server_id))
            if not token:
                raise ValueError('Reconnect this server to restore its Plex authorization.')
            logger.blacklist_config({'Plex': {'PLEX_TOKEN': token}})
            server = connect_plex_server(record['url'], token)
            if str(server.machineIdentifier) != server_id:
                raise ValueError('The address now belongs to a different Plex server. Reconnect it.')
            version = getattr(server, 'version', None)
            if isinstance(version, str) and version:
                with Session(storage.engine()) as session:
                    row = session.get(ServerRecord, server_id)
                    if row:
                        row.version = version[:64]
                        session.commit()
            _connections[server_id] = server
        return _connections[server_id]


def update_server(server_id: str, values: dict) -> None:
    """Update per-server processing settings.

    Parameters
    ----------
    server_id : str
        Plex machine identifier.
    values : dict
        Enabled flag, data directory, or ignored library IDs.
    """
    with Session(storage.engine()) as session:
        record = session.get(ServerRecord, server_id)
        if record is None:
            raise ValidationError(ValidationMessage.SERVER_NOT_FOUND)
        for key in ('enabled', 'data_directory', 'ignored_libraries'):
            if key in values:
                value = values[key]
                if key == 'enabled' and not isinstance(value, bool):
                    raise ValidationError(ValidationMessage.SERVER_ENABLED_INVALID)
                if key != 'enabled' and (not isinstance(value, str) or len(value) > 4096 or '\x00' in value):
                    raise ValidationError(ValidationMessage.SERVER_SETTING_INVALID)
                setattr(record, key, value)
        session.commit()


def record_refresh(server_id: str, error: str | None = None) -> None:
    """Record the last completed scan or a sanitized connection failure.

    Parameters
    ----------
    server_id : str
        Plex machine identifier.
    error : str or None, optional
        Public error text, cleared after a successful scan.
    """
    with Session(storage.engine()) as session:
        row = session.get(ServerRecord, server_id)
        if row:
            row.last_error = error
            if error is None:
                row.last_refresh = datetime.now(timezone.utc).isoformat(timespec='seconds')
            session.commit()


def remove_server(server_id: str) -> None:
    """Remove a connection, its credential, and only its cached state.

    Parameters
    ----------
    server_id : str
        Plex machine identifier.
    """
    from plex.plexapi import stop_plex_listener
    from plex import ssh

    stop_plex_listener(server_id)
    token_store.delete_token(credential_id(server_id))
    ssh.remove_settings(server_id)
    with _lock:
        _connections.pop(server_id, None)
        with Session(storage.engine()) as session:
            for model in (storage.LibraryItem, storage.LibrarySection, storage.ThemeRecord, storage.ThemeError):
                session.execute(delete(model).where(model.server_id == server_id))
            session.execute(delete(ServerRecord).where(ServerRecord.id == server_id))
            session.commit()


def clear_connections() -> None:
    """Discard cached connections after account changes or shutdown."""
    with _lock:
        _connections.clear()


def disconnect_account() -> None:
    """Erase credentials and pause saved servers while preserving upload history."""
    from plex.plexapi import stop_plex_listener

    stop_plex_listener()
    for record in list_servers():
        token_store.delete_token(credential_id(record['id']))
        update_server(record['id'], {'enabled': False})
        record_refresh(record['id'], 'Reconnect this server after linking your Plex account.')
    auth.disconnect()
    clear_connections()
