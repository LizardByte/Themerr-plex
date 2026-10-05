"""Refresh media-server dashboards without discarding offline snapshots."""

from common import logger
from media_servers import get_backend
from themerr import storage

log = logger.get_logger(__name__)


def cache_data() -> None:
    """Refresh enabled server dashboards independently without discarding offline snapshots."""
    backend = get_backend()
    registered = backend.list_servers(enabled_only=True)
    if not registered:
        return
    successful = True
    for record in registered:
        try:
            with storage.server_scope(record['id']):
                log.info('Refreshing dashboard for server %r (%s)', record['name'], record['id'])
                if not backend.server(record['id']).cache_dashboard():
                    successful = False
                    backend.record_refresh(record['id'], f'Dashboard refresh could not reach {backend.name}.')
                    continue
            backend.record_refresh(record['id'])
        except Exception:
            successful = False
            log.exception('Dashboard refresh failed for server %s', record['id'])
            backend.record_refresh(record['id'],
                                   f'Dashboard refresh failed. Check the {backend.name} address and access.')
    if successful:
        from common.notifications import refresh_completed
        refresh_completed()
