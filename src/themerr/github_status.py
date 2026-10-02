"""Persist the latest successful ThemerrDB deployment and an hourly GitHub check limit."""

# standard imports
from datetime import datetime, timezone
import json
from threading import Lock
import time

# lib imports
import requests
from sqlalchemy.orm import Session

# local imports
from common import logger
from themerr import storage

log = logger.get_logger(__name__)
_lock = Lock()
_CACHE_KEY = 'themerrdb_deployment'
_INTERVAL = 3600
_WORKFLOW_URL = 'https://github.com/LizardByte/ThemerrDB/actions/workflows/pages/pages-build-deployment'
# GitHub's built-in Pages workflow has no YAML filename; use its stable repository workflow ID.
_WORKFLOW_ID = 34813093


def _load() -> dict:
    """Load installation-wide deployment metadata from SQLite."""
    with Session(storage.engine()) as database:
        row = database.get(storage.AppSetting, _CACHE_KEY)
        try:
            data = json.loads(row.value) if row else {}
        except (ValueError, TypeError):
            return {}
        return data if isinstance(data, dict) else {}


def _save(data: dict) -> None:
    """Persist the attempt deadline before making an external request."""
    with Session(storage.engine()) as database:
        row = database.get(storage.AppSetting, _CACHE_KEY)
        if row is None:
            database.add(storage.AppSetting(key=_CACHE_KEY, value=json.dumps(data)))
        else:
            row.value = json.dumps(data)
        database.commit()


def publication_status() -> dict:
    """Return the last successful Pages deployment, checking at most once per hour.

    Checks are serialized across application threads. The attempt deadline is saved
    before the request, so failures and application restarts also respect the limit.
    Failed checks preserve the last known successful deployment.

    Returns
    -------
    dict
        Deployment completion date and workflow link, last attempt and next check timestamps,
        and whether the last check failed. Dates use UTC; timestamps use Unix seconds.
    """
    with _lock:
        state = _load()
        now = time.time()
        if now >= state.get('next_check', 0):
            state.update(checked_at=now, next_check=now + _INTERVAL, stale=True)
            _save(state)
            try:
                with requests.get(
                    f'https://api.github.com/repos/LizardByte/ThemerrDB/actions/workflows/{_WORKFLOW_ID}/runs',
                    params={'status': 'success', 'per_page': 1},
                    headers={'Accept': 'application/vnd.github+json'}, timeout=10, allow_redirects=False,
                ) as response:
                    response.raise_for_status()
                    if response.status_code != 200:
                        raise ValueError('Unexpected GitHub response')
                    runs = response.json()['workflow_runs']
                if not isinstance(runs, list):
                    raise ValueError('Invalid GitHub workflow list')
                if not runs:
                    state.pop('updated_at', None)
                    state.pop('run_id', None)
                    state['stale'] = False
                else:
                    run = runs[0]
                    run_id = run['id']
                    date = datetime.fromisoformat(run['updated_at'])
                    if (type(run_id) is not int or run_id <= 0 or date.tzinfo is None or
                            run['workflow_id'] != _WORKFLOW_ID or run['status'] != 'completed' or
                            run['conclusion'] != 'success'):
                        raise ValueError('Invalid GitHub deployment metadata')
                    state.update(updated_at=date.astimezone(timezone.utc).isoformat(), run_id=run_id, stale=False)
            except (requests.RequestException, ValueError, TypeError, KeyError) as error:
                log.warning('Unable to check ThemerrDB deployment (%s); retrying in one hour', type(error).__name__)
            _save(state)
        return {
            'updated_at': state.get('updated_at'),
            'url': ('https://github.com/LizardByte/ThemerrDB/actions/runs/' + str(state['run_id'])
                    if state.get('run_id') else _WORKFLOW_URL),
            'checked_at': state.get('checked_at'), 'next_check': state.get('next_check'),
            'stale': state.get('stale', True),
        }
