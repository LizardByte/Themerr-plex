"""SQLite persistence for dashboard, upload tracking, errors, and Plex sign-in."""

# standard imports
from contextlib import contextmanager
from contextvars import ContextVar
import os
from pathlib import Path
from threading import RLock

# lib imports
from alembic import command
from alembic.config import Config
from sqlalchemy import Boolean, ForeignKeyConstraint, Integer, String, create_engine, delete, func, select
from sqlalchemy.engine import URL, Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

# local imports
from common import config as app_config
from common import definitions

_lock = RLock()
_engine: Engine | None = None
_engine_path: str | None = None
_dashboard_lock = RLock()
_dashboard_revision = 0
_theme_uploads: dict[tuple[str, str], tuple[int, str]] = {}
_server_scope = ContextVar('media_server_id', default='default')


def current_server_id() -> str:
    """Return the server ID for the current worker or request.

    Returns
    -------
    str
        Saved server identity, or the default Plex scope.
    """
    return _server_scope.get()


@contextmanager
def server_scope(server_id: str):
    """Scope storage and integration operations to one server.

    Parameters
    ----------
    server_id : str
        Plex machine identifier.

    Yields
    ------
    None
        Operations inside the context use this server.
    """
    token = _server_scope.set(server_id)
    try:
        yield
    finally:
        _server_scope.reset(token)


class Base(DeclarativeBase):
    """Base for Themerr's persisted models."""


class LibrarySection(Base):
    """One cached media-server library section."""

    __tablename__ = 'library_sections'

    server_id: Mapped[str] = mapped_column(String, primary_key=True, default=current_server_id)

    key: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    agent: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    media_count: Mapped[int] = mapped_column(Integer, nullable=False)
    media_percent_complete: Mapped[int] = mapped_column(Integer, nullable=False)
    collection_count: Mapped[int] = mapped_column(Integer, nullable=False)
    collection_percent_complete: Mapped[int] = mapped_column(Integer, nullable=False)
    collections_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False)


class LibraryItem(Base):
    """One dashboard row keyed by its opaque server item identifier."""

    __tablename__ = 'library_items'

    server_id: Mapped[str] = mapped_column(String, primary_key=True, default=current_server_id)

    rating_key: Mapped[str] = mapped_column(String, primary_key=True)
    __table_args__ = (ForeignKeyConstraint(
        ['server_id', 'section_key'], ['library_sections.server_id', 'library_sections.key'],
    ),)

    section_key: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    year: Mapped[int | None] = mapped_column(Integer)
    agent: Mapped[str | None] = mapped_column(String)
    database: Mapped[str | None] = mapped_column(String)
    database_type: Mapped[str | None] = mapped_column(String)
    database_id: Mapped[str | None] = mapped_column(String)
    source_database: Mapped[str | None] = mapped_column(String)
    source_id: Mapped[str | None] = mapped_column(String)
    issue_action: Mapped[str | None] = mapped_column(String)
    issue_url: Mapped[str | None] = mapped_column(String)
    theme: Mapped[bool] = mapped_column(Boolean, nullable=False)
    theme_provider: Mapped[str | None] = mapped_column(String)
    theme_status: Mapped[str] = mapped_column(String, nullable=False)


class ThemeRecord(Base):
    """Theme metadata written by Themerr after a successful upload."""

    __tablename__ = 'theme_records'

    server_id: Mapped[str] = mapped_column(String, primary_key=True, default=current_server_id)

    rating_key: Mapped[str] = mapped_column(String, primary_key=True)
    item_type: Mapped[str] = mapped_column(String, nullable=False)
    youtube_theme_url: Mapped[str | None] = mapped_column(String)
    uploaded_theme_key: Mapped[str | None] = mapped_column(String)
    audio_codec: Mapped[str | None] = mapped_column(String)
    audio_sha256: Mapped[str | None] = mapped_column(String)
    mp4a_available: Mapped[bool | None] = mapped_column(Boolean)
    art_url: Mapped[str | None] = mapped_column(String)
    poster_url: Mapped[str | None] = mapped_column(String)


class ThemeError(Base):
    """Latest actionable processing failure for one Plex item."""

    __tablename__ = 'theme_errors'

    server_id: Mapped[str] = mapped_column(String, primary_key=True, default=current_server_id)

    rating_key: Mapped[str] = mapped_column(String, primary_key=True)
    reason: Mapped[str] = mapped_column(String, nullable=False)


class AppSetting(Base):
    """Non-secret installation settings and encrypted token data."""

    __tablename__ = 'app_settings'

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)


def database_path() -> str:
    """Return the SQLite path beside the active configuration file.

    Reuse the previous database when upgrading an existing installation.

    Returns
    -------
    str
        Absolute database path.
    """
    if app_config.CONFIG is not None and getattr(app_config.CONFIG, 'filename', None):
        directory = os.path.dirname(os.path.abspath(app_config.CONFIG.filename))
    else:
        directory = definitions.Paths.CONFIG_DIR
    path = os.path.join(directory, definitions.Files.DATABASE)
    legacy_path = os.path.join(directory, f'{definitions.Names.legacy_name.lower()}.db')
    return legacy_path if not os.path.exists(path) and os.path.isfile(legacy_path) else path


def _replace_dashboard(session: Session, sections: dict) -> None:
    """Replace the dashboard snapshot within the caller's transaction.

    Parameters
    ----------
    session : Session
        Active database session.
    sections : dict
        Complete library snapshot keyed by section ID.
    """
    session.execute(delete(LibraryItem).where(LibraryItem.server_id == current_server_id()))
    session.execute(delete(LibrarySection).where(LibrarySection.server_id == current_server_id()))
    for section in sections.values():
        session.add(LibrarySection(**{
            name: str(section[name]) if name == 'key' else section[name] for name in (
                'key', 'title', 'agent', 'type', 'media_count', 'media_percent_complete',
                'collection_count', 'collection_percent_complete', 'collections_enabled', 'total_count',
            )
        }))
        for position, item in enumerate(section['items']):
            fields = {name: item.get(name) for name in (
                'title', 'type', 'year', 'agent', 'database', 'database_type', 'database_id',
                'source_database', 'source_id', 'issue_action', 'issue_url', 'theme',
                'theme_provider', 'theme_status',
            )}
            if fields['database_id'] is not None:
                fields['database_id'] = str(fields['database_id'])
            session.add(LibraryItem(
                rating_key=str(item['rating_key']), section_key=str(section['key']), position=position, **fields,
            ))


def engine() -> Engine:
    """Open SQLite and apply schema migrations.

    Returns
    -------
    Engine
        Engine for the active configuration file.
    """
    global _engine, _engine_path
    path = os.path.abspath(database_path())
    with _lock:
        if _engine_path == path and _engine is not None:
            return _engine
        if _engine is not None:
            _engine.dispose()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        was_missing = not os.path.exists(path)
        candidate = create_engine(URL.create('sqlite', database=path), connect_args={'timeout': 30})
        try:
            migration_config = Config()
            migration_path = Path(__file__).resolve().parent / 'migrations'
            migration_config.set_main_option('script_location', str(migration_path).replace('%', '%%'))
            with candidate.begin() as connection:
                migration_config.attributes['connection'] = connection
                command.upgrade(migration_config, 'head')
            if was_missing and os.name != 'nt':
                os.chmod(path, 0o600)
        except Exception:
            candidate.dispose()
            raise
        _engine, _engine_path = candidate, path
        return candidate


def close() -> None:
    """Dispose the active engine, primarily for clean shutdown and tests."""
    global _engine, _engine_path, _dashboard_revision
    with _dashboard_lock:
        with _lock:
            if _engine is not None:
                _engine.dispose()
            _engine, _engine_path = None, None
        _dashboard_revision = 0
        _theme_uploads.clear()


def dashboard_revision() -> int:
    """Return the current upload revision before building a dashboard snapshot.

    Returns
    -------
    int
        Revision used to retain uploads that finish during the scan.
    """
    with _dashboard_lock:
        return _dashboard_revision


def _set_dashboard_theme_uploaded(session: Session, rating_key: str, provider: str) -> None:
    """Update one cached row and its library progress in a transaction."""
    item = session.get(LibraryItem, (current_server_id(), rating_key))
    if item is None:
        return
    item.theme = True
    item.theme_status = 'complete'
    item.theme_provider = provider

    section = session.get(LibrarySection, (current_server_id(), item.section_key))
    if item.type == 'collection':
        total = section.collection_count
        field = 'collection_percent_complete'
        type_filter = LibraryItem.type == 'collection'
    else:
        total = section.media_count
        field = 'media_percent_complete'
        type_filter = LibraryItem.type != 'collection'
    session.flush()
    complete = session.scalar(select(func.count()).select_from(LibraryItem).where(
        LibraryItem.server_id == current_server_id(), LibraryItem.section_key == item.section_key,
        type_filter, LibraryItem.theme.is_(True),
    ))
    setattr(section, field, int(complete / total * 100) if total else 0)


def mark_dashboard_theme_uploaded(rating_key: int | str, provider: str) -> None:
    """Publish a successful upload to the cached dashboard immediately.

    The revision also preserves uploads that finish while a full dashboard scan is in progress.

    Parameters
    ----------
    rating_key : int or str
        Plex rating key of the uploaded item.
    provider : str
        Provider identified after the upload.
    """
    global _dashboard_revision

    key = str(rating_key)
    with _dashboard_lock:
        with Session(engine()) as session:
            _set_dashboard_theme_uploaded(session, key, provider)
            session.commit()
        _dashboard_revision += 1
        _theme_uploads[(current_server_id(), key)] = (_dashboard_revision, provider)


def replace_dashboard(sections: dict, since_revision: int | None = None) -> None:
    """Atomically publish a complete dashboard snapshot.

    Parameters
    ----------
    sections : dict
        Complete library snapshot keyed by section ID.
    since_revision : int or None, optional
        Upload revision captured before the scan. Newer uploads are retained in the snapshot.
    """
    with _dashboard_lock, Session(engine()) as session:
        _replace_dashboard(session, sections)
        if since_revision is not None:
            for (server_id, key), (revision, provider) in _theme_uploads.items():
                if server_id == current_server_id() and revision > since_revision:
                    _set_dashboard_theme_uploaded(session, key, provider)
        session.commit()


def get_dashboard() -> dict | None:
    """Return the most recently published dashboard.

    Returns
    -------
    dict or None
        Library snapshot, or ``None`` before the first scan.
    """
    with Session(engine()) as session:
        sections = session.scalars(select(LibrarySection).where(
            LibrarySection.server_id == current_server_id()).order_by(LibrarySection.key)).all()
        if not sections:
            return None
        dashboard = {}
        for section in sections:
            items = session.scalars(select(LibraryItem).where(
                LibraryItem.server_id == current_server_id(), LibraryItem.section_key == section.key,
            ).order_by(LibraryItem.position)).all()
            dashboard[str(section.key)] = {
                **{name: getattr(section, name) for name in (
                    'key', 'title', 'agent', 'type', 'media_count', 'media_percent_complete',
                    'collection_count', 'collection_percent_complete', 'collections_enabled', 'total_count',
                )},
                'items': [{name: getattr(item, name) for name in (
                    'rating_key', 'title', 'type', 'year', 'agent', 'database', 'database_type',
                    'database_id', 'source_database', 'source_id', 'issue_action', 'issue_url',
                    'theme', 'theme_provider', 'theme_status',
                )} for item in items],
            }
        return dashboard


def get_tracking(rating_key: int | str) -> dict:
    """Return upload tracking fields for one Plex item.

    Parameters
    ----------
    rating_key : int or str
        Plex item rating key.

    Returns
    -------
    dict
        Known upload fields, or an empty dictionary.
    """
    with Session(engine()) as session:
        row = session.get(ThemeRecord, (current_server_id(), str(rating_key)))
        if row is None:
            return {}
        return {name: getattr(row, name) for name in (
            'youtube_theme_url', 'uploaded_theme_key', 'audio_codec', 'audio_sha256', 'mp4a_available',
            'art_url', 'poster_url',
        ) if getattr(row, name) is not None}


def save_tracking(rating_key: int | str, item_type: str, values: dict) -> None:
    """Upsert metadata after a successful Themerr upload.

    Parameters
    ----------
    rating_key : int or str
        Plex item rating key.
    item_type : str
        Plex item type.
    values : dict
        Upload fields to update.
    """
    allowed = {'youtube_theme_url', 'uploaded_theme_key', 'audio_codec', 'audio_sha256', 'mp4a_available',
               'art_url', 'poster_url'}
    with Session(engine()) as session:
        row = session.get(ThemeRecord, (current_server_id(), str(rating_key)))
        if row is None:
            row = ThemeRecord(rating_key=str(rating_key), item_type=item_type)
            session.add(row)
        for key, value in values.items():
            if key in allowed:
                setattr(row, key, value)
        session.commit()


def get_errors() -> dict[str, str]:
    """Return the latest recorded processing errors.

    Returns
    -------
    dict[str, str]
        Error reason by Plex rating key.
    """
    with Session(engine()) as session:
        return {row.rating_key: row.reason for row in session.scalars(
            select(ThemeError).where(ThemeError.server_id == current_server_id()))}


def set_error(rating_key: int | str, reason: str | None) -> None:
    """Save or clear one item failure.

    Parameters
    ----------
    rating_key : int or str
        Plex item rating key.
    reason : str or None
        Failure reason, or ``None`` to clear it.
    """
    with Session(engine()) as session:
        row = session.get(ThemeError, (current_server_id(), str(rating_key)))
        if reason:
            if row is None:
                session.add(ThemeError(rating_key=str(rating_key), reason=reason))
            else:
                row.reason = reason
        elif row is not None:
            session.delete(row)
        session.commit()


def get_credentials() -> dict[str, str]:
    """Return the stored Plex OAuth client identifier.

    Returns
    -------
    dict[str, str]
        Present credential fields.
    """
    with Session(engine()) as session:
        return {row.key: row.value for row in session.scalars(select(AppSetting))
                if row.key == 'client_id'}


def save_credentials(credentials: dict[str, str]) -> None:
    """Replace the non-secret Plex OAuth client identifier.

    Parameters
    ----------
    credentials : dict[str, str]
        Client identifier.
    """
    with Session(engine()) as session:
        row = session.get(AppSetting, 'client_id')
        if 'client_id' not in credentials:
            if row is not None:
                session.delete(row)
        elif row is None:
            session.add(AppSetting(key='client_id', value=credentials['client_id']))
        else:
            row.value = credentials['client_id']
        session.commit()


def get_encrypted_token(namespace: str = '') -> str:
    """Return encrypted token data for the external-key backend.

    Parameters
    ----------
    namespace : str, optional
        Separate credential slot for a server token.

    Returns
    -------
    str
        Fernet ciphertext, or an empty string when not signed in.
    """
    with Session(engine()) as session:
        row = session.get(AppSetting, 'plex_token_ciphertext' + namespace)
        return row.value if row is not None else ''


def save_encrypted_token(ciphertext: str | None, namespace: str = '') -> None:
    """Save or clear encrypted token data.

    Parameters
    ----------
    ciphertext : str or None
        Fernet ciphertext, or ``None`` to disconnect.
    namespace : str, optional
        Separate credential slot for a server token.
    """
    with Session(engine()) as session:
        row = session.get(AppSetting, 'plex_token_ciphertext' + namespace)
        if ciphertext is None:
            if row is not None:
                session.delete(row)
        elif row is None:
            session.add(AppSetting(key='plex_token_ciphertext' + namespace, value=ciphertext))
        else:
            row.value = ciphertext
        session.commit()
