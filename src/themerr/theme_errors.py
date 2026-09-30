"""Persist recent theme processing errors for the dashboard."""

# standard imports
import json
import os
import tempfile
from threading import Lock

# local imports
from common import definitions
from common import logger

log = logger.get_logger(__name__)
_lock = Lock()


def _path() -> str:
    """Return the path to the theme error record."""
    return os.path.join(definitions.Paths.CONFIG_DIR, 'theme_errors.json')


def _read() -> dict[str, str]:
    """Read saved errors while the caller holds the lock."""
    try:
        with open(_path(), encoding='utf-8') as source:
            data = json.load(source)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        log.warning('Unable to read theme errors: %s', exc)
        return {}
    return data if isinstance(data, dict) else {}


def get_errors() -> dict[str, str]:
    """Return the saved errors indexed by Plex rating key."""
    with _lock:
        return _read()


def set_error(rating_key: int | str, reason: str | None) -> None:
    """Save or clear the latest processing error for a Plex item.

    Parameters
    ----------
    rating_key : int or str
        Plex item rating key.
    reason : str or None
        Human-readable error, or ``None`` to clear a previous error.
    """
    with _lock:
        errors = _read()
        key = str(rating_key)
        if reason:
            errors[key] = reason
        elif key in errors:
            del errors[key]
        else:
            return

        temporary_path = None
        try:
            os.makedirs(definitions.Paths.CONFIG_DIR, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=definitions.Paths.CONFIG_DIR,
                                             delete=False) as target:
                temporary_path = target.name
                json.dump(errors, target)
            os.replace(temporary_path, _path())
        except OSError as exc:
            log.warning('Unable to save theme errors: %s', exc)
            if temporary_path:
                try:
                    os.remove(temporary_path)
                except OSError:
                    pass
