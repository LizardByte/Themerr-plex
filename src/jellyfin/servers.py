"""Persist independent Jellyfin connections without plaintext credentials."""

from datetime import datetime, timezone
from uuid import uuid4
from threading import RLock

from sqlalchemy import Boolean, String, delete, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from common import credentials, logger
from common.validation import ValidationError, ValidationMessage
from jellyfin.client import Client, base_url, identifier
from media_servers.base import MediaServerError
from themerr import storage

_credential_lock = RLock()
_SERVER_PREFIX = 'jellyfin:'


class ServerRecord(storage.Base):
    """Public Jellyfin connection settings; the API key lives in the secure store."""

    __tablename__ = 'jellyfin_servers'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[str] = mapped_column(String, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ignored_libraries: Mapped[str] = mapped_column(String, nullable=False, default='')
    last_refresh: Mapped[str | None] = mapped_column(String)
    last_error: Mapped[str | None] = mapped_column(String)


def list_servers(enabled_only=False):
    """Read saved connection settings without exposing API keys."""
    with Session(storage.engine()) as session:
        query = select(ServerRecord).order_by(ServerRecord.name)
        if enabled_only:
            query = query.where(ServerRecord.enabled.is_(True))
        return [{c.name: getattr(row, c.name) for c in ServerRecord.__table__.columns}
                for row in session.scalars(query)]


def get_server(server_id):
    """Find a Jellyfin connection by its namespaced identity."""
    return next((row for row in list_servers() if row['id'] == server_id), None)


def credential_id(server_id):
    """Separate server keys by installation, including shared headless vaults."""
    with _credential_lock, Session(storage.engine()) as session:
        row = session.get(storage.AppSetting, 'jellyfin_client_id')
        if row is None:
            row = storage.AppSetting(key='jellyfin_client_id', value=uuid4().hex)
            session.add(row)
            session.commit()
        return _SERVER_PREFIX + row.value + ':' + server_id


def add_server(url, token):
    """Verify the server and save its API key separately from public settings."""
    url = base_url(url)
    if not isinstance(token, str) or not token or len(token) > 256 or any(ord(c) <= 32 for c in token):
        raise MediaServerError('Enter a valid Jellyfin API key.', 400)
    logger.blacklist_config({'Jellyfin': {'API_TOKEN': token}})
    info = Client(url, token).json('GET', '/System/Info')
    try:
        server_id = _SERVER_PREFIX + identifier(info['Id'])
        name, version = str(info['ServerName'])[:128], str(info['Version'])[:32]
    except (KeyError, TypeError) as exc:
        raise MediaServerError('Jellyfin did not provide valid server information.', 502) from exc
    from jellyfin.connector import profile
    profile(version)
    credentials.save_token(credential_id(server_id), token)
    with Session(storage.engine()) as session:
        row = session.get(ServerRecord, server_id)
        if row is None:
            row = ServerRecord(id=server_id, enabled=True, ignored_libraries='')
            session.add(row)
        row.name, row.url, row.version = name, url, version
        session.commit()
    return get_server(server_id)


def client(server_id):
    """Open a saved enabled connection and verify that its address still matches."""
    record = get_server(server_id)
    if record is None:
        raise MediaServerError('Server not found.', 404)
    if not record['enabled']:
        raise MediaServerError('This Jellyfin server is paused.', 409)
    token = credentials.get_token(credential_id(server_id))
    if not token:
        raise MediaServerError('Reconnect this server to restore its Jellyfin API key.', 503)
    connection = Client(record['url'], token)
    info = connection.json('GET', '/System/Info')
    if _SERVER_PREFIX + identifier(info.get('Id')) != server_id:
        raise MediaServerError('This address now belongs to a different Jellyfin server.', 409)
    return connection


def update_server(server_id, values):
    """Validate processing settings without accepting credentials as preferences."""
    with Session(storage.engine()) as session:
        row = session.get(ServerRecord, server_id)
        if row is None:
            raise ValidationError(ValidationMessage.SERVER_NOT_FOUND)
        if 'enabled' in values:
            if not isinstance(values['enabled'], bool):
                raise ValidationError(ValidationMessage.SERVER_ENABLED_INVALID)
            row.enabled = values['enabled']
        if 'ignored_libraries' in values:
            value = values['ignored_libraries']
            if not isinstance(value, str) or len(value) > 8192:
                raise ValidationError(ValidationMessage.SERVER_SETTING_INVALID)
            row.ignored_libraries = ','.join(identifier(part.strip()) for part in value.split(',') if part.strip())
        session.commit()


def record_refresh(server_id, error=None):
    """Record only sanitized failures and successful refresh timestamps."""
    with Session(storage.engine()) as session:
        row = session.get(ServerRecord, server_id)
        if row:
            row.last_error = error
            if error is None:
                row.last_refresh = datetime.now(timezone.utc).isoformat(timespec='seconds')
            session.commit()


def remove_server(server_id):
    """Remove local history and credentials while retaining media on Jellyfin."""
    credentials.delete_token(credential_id(server_id))
    with Session(storage.engine()) as session:
        for model in (storage.LibraryItem, storage.LibrarySection, storage.ThemeRecord, storage.ThemeError):
            session.execute(delete(model).where(model.server_id == server_id))
        session.execute(delete(ServerRecord).where(ServerRecord.id == server_id))
        session.commit()
