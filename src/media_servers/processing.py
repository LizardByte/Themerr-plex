"""Server-scoped theme queue and scan orchestration."""

# standard imports
import queue
import threading

# local imports
from common import config, logger
from media_servers import get_backend
from themerr import storage

log = logger.get_logger(__name__)
_active_items: set[tuple[str, str]] = set()


class _WorkQueue(queue.Queue):
    """Mark dequeued items active while the queue lock is still held."""

    def _get(self):
        work = super()._get()
        _active_items.add(work)
        return work


q = _WorkQueue()


def enqueue(item_id: str) -> bool:
    """Queue an item once within the current server's storage scope.

    Parameters
    ----------
    item_id : str
        Opaque media-server item identifier.

    Returns
    -------
    bool
        Whether new work was queued, including active-work deduplication.
    """
    work = (
        storage.current_server_id(),
        str(item_id),
    )
    with q.mutex:
        if work in q.queue or work in _active_items:
            return False
        q._put(work)
        q.unfinished_tasks += 1
        q.not_empty.notify()
    return True


def process_queue() -> None:
    """Process queued items independently, releasing active work even on failure."""
    while True:
        server_id, item_id = q.get()
        try:
            backend = get_backend()
            with storage.server_scope(server_id):
                if server_id == 'default' or (backend.get_server(server_id) or {}).get('enabled'):
                    backend.server(server_id).update_item(item_id)
        except Exception:
            log.exception('Unexpected error processing item %s on server %s', item_id, server_id)
        finally:
            with q.mutex:
                _active_items.discard(
                    (
                        server_id,
                        item_id,
                    )
                )
            q.task_done()


def start_queue_threads() -> None:
    """Start the configured number of daemon theme-processing workers."""
    # Preserve the existing preference key and its configured value.
    for _ in range(max(1, int(config.CONFIG['Themerr']['INT_PLEXAPI_UPLOAD_THREADS']))):
        try:
            threading.Thread(target=process_queue, daemon=True).start()
        except RuntimeError:
            log.exception('Unable to start a theme-processing worker')
            break


def scheduled_update() -> None:
    """Scan enabled connections while isolating unavailable servers."""
    if not config.CONFIG['Themerr']['BOOL_THEMERR_ENABLED']:
        return
    backend = get_backend()
    for record in backend.list_servers(enabled_only=True):
        try:
            with storage.server_scope(record['id']):
                log.info('Scanning server %r (%s)', record['name'], record['id'])
                backend.server(record['id']).scan(enqueue)
        except Exception:
            log.exception('Theme scan failed for server %s', record['id'])
            backend.record_refresh(
                record['id'], f'Theme scan could not reach {backend.name}. Check its address and access.'
            )
