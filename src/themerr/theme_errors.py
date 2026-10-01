"""Theme processing failures exposed to the dashboard."""

# standard imports
import re

# local imports
from themerr import storage


def is_video_issue(reason: str | None) -> bool:
    """Distinguish a broken source video from local connection or regional failures.

    Parameters
    ----------
    reason : str or None
        Latest sanitized theme failure.

    Returns
    -------
    bool
        Whether replacing the ThemerrDB video is an appropriate action.

    Notes
    -----
    ThemerrDB checks US availability when accepting a theme. A regional failure
    on this installation alone does not establish that the US source is broken.
    """
    if not reason:
        return False
    reason = reason.casefold()
    if re.search(r'(?:not available|unavailable|blocked).*\b(?:united states|usa|us)\b', reason):
        return True
    if re.search(r'country|countries|region|geo.?restrict|geographic', reason):
        return False
    return bool(re.search(r'video (?:is )?(?:unavailable|not available|private|removed|deleted)|private video|'
                          r'has been (?:removed|deleted)|no longer available|age.?restrict|'
                          r'copyright|members.only|sign in to confirm your age', reason))


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
