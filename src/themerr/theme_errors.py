"""Theme processing failures exposed to the dashboard."""

# standard imports
import re

# local imports
from themerr import storage


def normalize_reason(error: Exception | str) -> str:
    """Return a concise failure reason without URLs or control characters."""
    reason = re.sub(r'https?://\S+', '[URL]', str(error))
    return re.sub(r'\s+', ' ', reason).strip()[:300] or 'Theme processing failed'


def get_errors() -> dict[str, str]:
    """Return the latest processing failures by Plex rating key."""
    return storage.get_errors()


def set_error(rating_key: int | str, reason: str | None) -> None:
    """Save or clear the latest processing failure for an item.

    Parameters
    ----------
    rating_key : int or str
        Plex item rating key.
    reason : str or None
        Failure message, or ``None`` to clear it.
    """
    storage.set_error(rating_key, normalize_reason(reason) if reason else None)
