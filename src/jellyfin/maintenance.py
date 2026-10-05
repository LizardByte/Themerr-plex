"""Keep bundled connectors current and defer their restarts until playback finishes."""

import json
from threading import Event, RLock, Thread
import time

from sqlalchemy.orm import Session

from common import config, logger
from jellyfin import connector, servers
from media_servers.base import MediaServerError
from themerr import storage

log = logger.get_logger(__name__)
_lock = RLock()
_stop = Event()
_thread = None
_STATE_PREFIX = 'jellyfin_connector_state:'


def state(server_id):
    """Read restart progress without exposing credentials."""
    with Session(storage.engine()) as session:
        row = session.get(storage.AppSetting, _STATE_PREFIX + server_id)
        return json.loads(row.value) if row else {}


def _save(server_id, **values):
    """Persist pending restarts so a Themerr restart does not lose their progress."""
    with Session(storage.engine()) as session:
        key = _STATE_PREFIX + server_id
        row = session.get(storage.AppSetting, key)
        current = json.loads(row.value) if row else {}
        current.update(values)
        if row is None:
            row = storage.AppSetting(key=key, value='')
            session.add(row)
        row.value = json.dumps(current)
        session.commit()
    return current


def install(server_id, url):
    """Install the exact connector and announce the pending restart before it happens."""
    with _lock:
        connection = servers.client(server_id)
        result = connector.install(connection, url)
        restart = result['restart_required']
        legacy_removed = False
        if config.CONFIG['Jellyfin']['REMOVE_LEGACY_PLUGIN']:
            legacy_removed = connector.remove_legacy(connection)
            restart = legacy_removed or restart
        legacy_checked = connector.bundle()['build'] if config.CONFIG['Jellyfin']['REMOVE_LEGACY_PLUGIN'] else None
        if restart:
            action = ('Connector replacement needs a restart before installation.' if result.get('reinstall_required')
                      else 'Connector installed.')
            message = action + ' Jellyfin will restart when playback finishes.'
            if not config.CONFIG['Jellyfin']['WAIT_FOR_IDLE']:
                message = action + ' Jellyfin will restart shortly.'
            if not config.CONFIG['Jellyfin']['AUTO_RESTART']:
                message = action + ' Automatic restarts are disabled; restart Jellyfin to continue.'
            _save(server_id, phase='pending', message=message, restart_required=True,
                  restart_after=time.time() + 30, build=connector.bundle()['build'], force_restart=legacy_removed,
                  legacy_checked=legacy_checked, reinstall_required=result.get('reinstall_required', False),
                  repository_url=url, manual_restart=False)
            log.info('%s (%s)', message, server_id)
            result['message'] = message
        else:
            _save(server_id, phase='active', message=result['message'], restart_required=False, force_restart=False,
                  legacy_checked=legacy_checked, reinstall_required=False, manual_restart=False)
        return {**result, 'restart_required': restart}


def _restart(server_id, connection, current):
    """Restart only a known pending connector after the notice and idle checks."""
    if (_stop.is_set() or not config.CONFIG['Jellyfin']['AUTO_RESTART'] or
            time.time() < current.get('restart_after', 0)):
        return
    if config.CONFIG['Jellyfin']['WAIT_FOR_IDLE']:
        sessions = connection.json('GET', '/Sessions')
        if not isinstance(sessions, list):
            raise MediaServerError('Jellyfin returned an invalid session list; restart deferred.', 502)
        if any(not isinstance(session, dict) for session in sessions):
            raise MediaServerError('Jellyfin returned an invalid session list; restart deferred.', 502)
        if any(session.get('NowPlayingItem') for session in sessions):
            _save(server_id, message='Waiting for Jellyfin playback to finish before restarting.')
            return
    info = connection.json('GET', '/System/Info')
    if info.get('CanSelfRestart') is False:
        _save(server_id, phase='manual', message='This Jellyfin installation cannot restart itself. '
              'Restart its service or container to load the connector.')
        return
    if _stop.is_set():
        return
    _save(server_id, phase='restarting', message='Restarting Jellyfin to load the connector.',
          restart_started=time.time())
    log.info('Restarting Jellyfin for the connector (%s)', server_id)
    # A closed connection can mean that Jellyfin already accepted the restart.
    try:
        connection.request('POST', '/System/Restart').close()
    except MediaServerError as exc:
        if exc.status_code != 502:
            raise


def force_restart(server_id):
    """Honor an explicit server-card restart, bypassing automatic delays and idle preferences."""
    with _lock:
        connection = servers.client(server_id)
        info = connection.json('GET', '/System/Info')
        if not isinstance(info, dict) or info.get('CanSelfRestart') is not True:
            raise MediaServerError('This Jellyfin installation cannot restart itself. '
                                   'Restart its service or container instead.', 409)
        current = state(server_id)
        log.info('Administrator requested an immediate Jellyfin restart (%s)', server_id)
        try:
            connection.request('POST', '/System/Restart').close()
        except MediaServerError as exc:
            if exc.status_code != 502:
                raise
        return _save(server_id, phase='restarting', restart_required=current.get('restart_required', False),
                     force_restart=current.get('force_restart', False), manual_restart=True,
                     restart_started=time.time(), build=current.get('build'),
                     message='Restarting Jellyfin. Active playback may be interrupted.')


def maintain(server_id):
    """Advance one connection's installation or restart without blocking other work."""
    with _lock:
        current = state(server_id)
        connection = servers.client(server_id)
        if current.get('phase') == 'restarting':
            try:
                _verify_loaded(connection, current)
            except MediaServerError:
                if time.time() - current['restart_started'] > 180:
                    _save(server_id, phase='manual', message='Jellyfin has not loaded the connector after restarting. '
                          'Check its service or container and restart it manually.')
                return
            if current.get('reinstall_required'):
                install(server_id, current['repository_url'])
                return
            from jellyfin.backend import JellyfinMediaServer
            JellyfinMediaServer(server_id).cache_dashboard()
            servers.record_refresh(server_id)
            message = 'Jellyfin restarted. Libraries refreshed.' if current.get('manual_restart') else \
                'Matching connector is active. Libraries refreshed.'
            _save(server_id, phase='active', message=message,
                  restart_required=False, force_restart=False, manual_restart=False)
            return
        if current.get('restart_required') and current.get('build') == connector.bundle()['build']:
            try:
                _verify_loaded(connection, current)
            except MediaServerError:
                if current.get('phase') != 'manual':
                    _restart(server_id, connection, current)
                return
            if current.get('reinstall_required'):
                install(server_id, current['repository_url'])
                return
            from jellyfin.backend import JellyfinMediaServer
            JellyfinMediaServer(server_id).cache_dashboard()
            servers.record_refresh(server_id)
            _save(server_id, phase='active', message='Matching connector is active. Libraries refreshed.',
                  restart_required=False, force_restart=False)
            return
        if not config.CONFIG['Jellyfin']['AUTO_UPDATE_CONNECTOR']:
            return
        url = connector.repository_url(required=False)
        if not url:
            return
        try:
            connector.verify(connection)
        except MediaServerError:
            if not _stop.is_set():
                install(server_id, url)
        else:
            if (config.CONFIG['Jellyfin']['REMOVE_LEGACY_PLUGIN'] and
                    current.get('legacy_checked') != connector.bundle()['build'] and not _stop.is_set()):
                install(server_id, url)


def _verify_loaded(connection, current):
    """Require legacy cleanup's restart even when the matching connector was already active."""
    if current.get('reinstall_required'):
        info = connection.json('GET', '/System/Info')
        if not isinstance(info, dict) or info.get('HasPendingRestart') is not False:
            raise MediaServerError('Restart Jellyfin before replacing the loaded connector.', 409)
        return
    if current.get('manual_restart') and not current.get('restart_required'):
        connection.json('GET', '/System/Info')
        return
    connector.verify(connection)
    if current.get('force_restart'):
        info = connection.json('GET', '/System/Info')
        if not isinstance(info, dict) or info.get('HasPendingRestart') is not False:
            raise MediaServerError('Restart Jellyfin to complete legacy plugin removal.', 409)


def reconcile():
    """Check enabled servers independently and retain fixed, actionable failure messages."""
    for server in servers.list_servers(enabled_only=True):
        if _stop.is_set():
            return
        try:
            maintain(server['id'])
        except MediaServerError as exc:
            current = state(server['id'])
            if current.get('phase') == 'restarting':
                if time.time() - current['restart_started'] <= 180:
                    continue
                _save(server['id'], phase='manual', message='Jellyfin did not become available after restarting. '
                      'Check its service or container.')
                continue
            _save(server['id'], message=str(exc))
            log.warning('Jellyfin connector maintenance: %s (%s)', str(exc), server['id'])
        except Exception as exc:
            log.warning('Jellyfin connector maintenance failed (%s)', type(exc).__name__)


def start():
    """Start one maintenance worker; repeated settings saves reuse it."""
    global _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            return
        _stop.clear()

        def loop():
            while not _stop.is_set():
                reconcile()
                _stop.wait(30)

        _thread = Thread(target=loop, name='Jellyfin connector maintenance', daemon=True)
        _thread.start()


def stop():
    """Signal the worker to stop before application shutdown."""
    _stop.set()
