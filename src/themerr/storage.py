"""SQLite persistence for dashboard, upload tracking, errors, and Plex sign-in."""

# standard imports
import json
import os
from pathlib import Path
from threading import RLock

# lib imports
from alembic import command
from alembic.config import Config
from sqlalchemy import Boolean, ForeignKey, Integer, String, create_engine, delete, select
from sqlalchemy.engine import URL, Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

# local imports
from common import config as app_config
from common import definitions
from common import logger

log = logger.get_logger(__name__)
_lock = RLock()
_engine: Engine | None = None
_engine_path: str | None = None


class Base(DeclarativeBase):
    """Base for Themerr's persisted models."""


class LibrarySection(Base):
    """One cached Plex library section."""

    __tablename__ = 'library_sections'

    key: Mapped[int] = mapped_column(Integer, primary_key=True)
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
    """One dashboard row keyed by its stable Plex rating key."""

    __tablename__ = 'library_items'

    rating_key: Mapped[str] = mapped_column(String, primary_key=True)
    section_key: Mapped[int] = mapped_column(ForeignKey('library_sections.key'), nullable=False)
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

    rating_key: Mapped[str] = mapped_column(String, primary_key=True)
    item_type: Mapped[str] = mapped_column(String, nullable=False)
    settings_hash: Mapped[str | None] = mapped_column(String)
    youtube_theme_url: Mapped[str | None] = mapped_column(String)
    uploaded_theme_key: Mapped[str | None] = mapped_column(String)
    art_url: Mapped[str | None] = mapped_column(String)
    poster_url: Mapped[str | None] = mapped_column(String)


class ThemeError(Base):
    """Latest actionable processing failure for one Plex item."""

    __tablename__ = 'theme_errors'

    rating_key: Mapped[str] = mapped_column(String, primary_key=True)
    reason: Mapped[str] = mapped_column(String, nullable=False)


class AppSetting(Base):
    """Small installation settings, including the Plex OAuth client and token."""

    __tablename__ = 'app_settings'

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)


def database_path() -> str:
    """Return the SQLite path beside the active configuration file.

    Returns
    -------
    str
        Absolute database path.
    """
    if app_config.CONFIG is not None and getattr(app_config.CONFIG, 'filename', None):
        return os.path.join(os.path.dirname(os.path.abspath(app_config.CONFIG.filename)), 'themerr-plex.db')
    return os.path.join(definitions.Paths.CONFIG_DIR, 'themerr-plex.db')


def _legacy_json(path: Path) -> dict:
    """Read one former JSON state file without changing it.

    Parameters
    ----------
    path : Path
        Former state file.

    Returns
    -------
    dict
        JSON object, or an empty dictionary if unreadable.
    """
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        log.warning('Unable to migrate %s: %s', path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def _replace_dashboard(session: Session, sections: dict) -> None:
    """Replace the dashboard snapshot within the caller's transaction.

    Parameters
    ----------
    session : Session
        Active database session.
    sections : dict
        Complete library snapshot keyed by section ID.
    """
    session.execute(delete(LibraryItem))
    session.execute(delete(LibrarySection))
    for section in sections.values():
        session.add(LibrarySection(**{
            name: section[name] for name in (
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
            if fields['theme_provider'] == 'themerr_inferred':
                fields['theme_provider'] = 'uploaded'
            session.add(LibraryItem(
                rating_key=str(item['rating_key']), section_key=int(section['key']), position=position, **fields,
            ))


def _import_legacy(engine: Engine) -> None:
    """Copy existing JSON state into SQLite once.

    Parameters
    ----------
    engine : Engine
        Migrated SQLite engine.
    """
    config_dir = Path(database_path()).parent
    with Session(engine) as session:
        if session.get(AppSetting, 'legacy_imported') is not None:
            return
        dashboard = config_dir / 'database_cache.json'
        if dashboard.is_file() and not session.scalar(select(LibrarySection.key).limit(1)):
            sections = _legacy_json(dashboard)
            if sections:
                try:
                    _replace_dashboard(session, sections)
                    session.flush()
                except (KeyError, TypeError, ValueError, SQLAlchemyError) as exc:
                    session.rollback()
                    log.warning('Unable to migrate dashboard cache: %s', exc)

        errors = config_dir / 'theme_errors.json'
        if errors.is_file():
            for key, reason in _legacy_json(errors).items():
                if isinstance(reason, str) and session.get(ThemeError, str(key)) is None:
                    session.add(ThemeError(rating_key=str(key), reason=reason))

        data_dir = config_dir / 'data'
        if data_dir.is_dir():
            item_types = {'Movies': 'movie', 'Collections': 'collection', 'TV Shows': 'show',
                          'Albums': 'album', 'Artists': 'artist'}
            for item_type_dir in data_dir.iterdir():
                item_type = item_types.get(item_type_dir.name)
                if not item_type or not item_type_dir.is_dir():
                    continue
                for path in item_type_dir.glob('*.json'):
                    if session.get(ThemeRecord, path.stem) is None:
                        data = _legacy_json(path)
                        if data:
                            session.add(ThemeRecord(rating_key=path.stem, item_type=item_type,
                                                    **{name: data.get(name) for name in (
                                                        'settings_hash', 'youtube_theme_url', 'art_url', 'poster_url',
                                                    )}))

        if app_config.CONFIG is not None:
            credentials_path = Path(app_config.CONFIG.filename).resolve().parent / 'plex-auth.json'
            if credentials_path.is_file():
                for key, value in _legacy_json(credentials_path).items():
                    if (key in ('client_id', 'token') and isinstance(value, str) and
                            session.get(AppSetting, key) is None):
                        session.add(AppSetting(key=key, value=value))
        session.add(AppSetting(key='legacy_imported', value='1'))
        session.commit()


def engine() -> Engine:
    """Open SQLite, apply migrations, and import older JSON state once.

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
            _import_legacy(candidate)
        except Exception:
            candidate.dispose()
            raise
        _engine, _engine_path = candidate, path
        return candidate


def close() -> None:
    """Dispose the active engine, primarily for clean shutdown and tests."""
    global _engine, _engine_path
    with _lock:
        if _engine is not None:
            _engine.dispose()
        _engine, _engine_path = None, None


def replace_dashboard(sections: dict) -> None:
    """Atomically publish a complete dashboard snapshot.

    Parameters
    ----------
    sections : dict
        Complete library snapshot keyed by section ID.
    """
    with Session(engine()) as session:
        _replace_dashboard(session, sections)
        session.commit()


def get_dashboard() -> dict | None:
    """Return the most recently published dashboard.

    Returns
    -------
    dict or None
        Library snapshot, or ``None`` before the first scan.
    """
    with Session(engine()) as session:
        sections = session.scalars(select(LibrarySection).order_by(LibrarySection.key)).all()
        if not sections:
            return None
        dashboard = {}
        for section in sections:
            items = session.scalars(select(LibraryItem).where(LibraryItem.section_key == section.key)
                                    .order_by(LibraryItem.position)).all()
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
        row = session.get(ThemeRecord, str(rating_key))
        if row is None:
            return {}
        return {name: getattr(row, name) for name in (
            'settings_hash', 'youtube_theme_url', 'uploaded_theme_key', 'art_url', 'poster_url',
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
    allowed = {'settings_hash', 'youtube_theme_url', 'uploaded_theme_key', 'art_url', 'poster_url'}
    with Session(engine()) as session:
        row = session.get(ThemeRecord, str(rating_key))
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
        return {row.rating_key: row.reason for row in session.scalars(select(ThemeError))}


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
        row = session.get(ThemeError, str(rating_key))
        if reason:
            if row is None:
                session.add(ThemeError(rating_key=str(rating_key), reason=reason))
            else:
                row.reason = reason
        elif row is not None:
            session.delete(row)
        session.commit()


def get_credentials() -> dict[str, str]:
    """Return the stored Plex OAuth client identifier and token.

    Returns
    -------
    dict[str, str]
        Present credential fields.
    """
    with Session(engine()) as session:
        return {row.key: row.value for row in session.scalars(select(AppSetting))
                if row.key in ('client_id', 'token')}


def save_credentials(credentials: dict[str, str]) -> None:
    """Replace the stored Plex OAuth credentials.

    Parameters
    ----------
    credentials : dict[str, str]
        Client identifier and optional token.
    """
    with Session(engine()) as session:
        for key in ('client_id', 'token'):
            row = session.get(AppSetting, key)
            if key not in credentials:
                if row is not None:
                    session.delete(row)
            elif row is None:
                session.add(AppSetting(key=key, value=credentials[key]))
            else:
                row.value = credentials[key]
        session.commit()
