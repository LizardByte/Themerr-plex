"""Authenticated server management, discovery, and dashboard views."""

# lib imports
from flask import Blueprint, abort, jsonify, render_template, request

# local imports
from plex import auth, plexapi, servers
from themerr import storage

blueprint = Blueprint('server_ui', __name__)


def _payload() -> dict:
    """Reject JSON arrays and scalar values at the API boundary."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        abort(400)
    return payload


def dashboard() -> tuple[dict, dict, dict]:
    """Assemble library snapshots without merging rating keys from different servers.

    Returns
    -------
    tuple of dict
        Libraries, scoped errors, and real summary counts.
    """
    libraries, errors = {}, {}
    registered = servers.list_servers()
    records = registered
    for record in records:
        with storage.server_scope(record['id']):
            snapshot = storage.get_dashboard() or {}
            failures = storage.get_errors()
        for key, section in snapshot.items():
            identity = record['id'] + ':' + key
            libraries[identity] = {**section, 'server_id': record['id'], 'server_name': record['name'],
                                   'enabled': record['enabled']}
            for item in section['items']:
                item['server_id'] = record['id']
                item['error'] = failures.get(item['rating_key'])
                errors[record['id'] + ':' + item['rating_key']] = item['error']
    items = [item for section in libraries.values() for item in section['items']]
    installed = sum(item['theme'] for item in items)
    return libraries, errors, {'total': len(items), 'installed': installed,
                               'coverage': round(installed / len(items) * 100) if items else 0,
                               'attention': sum(bool(item['error']) or item['theme_status'] in ('failed', 'unresolved')
                                                for item in items), 'servers': len(registered),
                               'libraries': len(libraries)}


@blueprint.route('/servers')
def server_page():
    """Render saved connections and discovery options.

    Returns
    -------
    str
        Server management page.
    """
    return render_template('servers.html', title='Servers', servers=servers.list_servers(),
                           plex_connected=bool(auth.get_token()))


@blueprint.route('/api/servers/discover', methods=['POST'])
def discover():
    """List account or LAN resources without disclosing access tokens.

    Returns
    -------
    Response
        Safe discovery results or a connection error.
    """
    payload = _payload()
    source = payload.get('source')
    if source not in ('account', 'local'):
        return jsonify({'message': 'Choose account or local discovery.'}), 400
    try:
        resources = servers.discover_account() if source == 'account' else servers.discover_local()
    except Exception:
        return jsonify({'message': 'Discovery failed. Check the Plex connection, or enter an address manually.'}), 502
    return jsonify({'servers': resources})


@blueprint.route('/api/servers', methods=['POST'])
def add_server():
    """Connect to a selected or manually addressed server.

    Returns
    -------
    Response
        Saved public settings or a sanitized failure.
    """
    payload = _payload()
    try:
        record = servers.add_server(payload.get('url', ''), payload.get('resource_id'))
    except ValueError as exc:
        return jsonify({'message': str(exc)}), 400
    except OSError:
        return jsonify({'message': 'Unable to save the Plex token. Check the configured credential store.'}), 500
    except Exception:
        return jsonify({'message': 'Could not reach this Plex server. Check the address and account access.'}), 502
    plexapi.plex_listener()
    _refresh()
    return jsonify({'server': record}), 201


@blueprint.route('/api/servers/<server_id>', methods=['POST', 'DELETE'])
def edit_server(server_id: str):
    """Save processing preferences or remove a server.

    Parameters
    ----------
    server_id : str
        Plex machine identifier.

    Returns
    -------
    Response
        Updated settings or removal result.
    """
    if not servers.get_server(server_id):
        return jsonify({'message': 'Server not found.'}), 404
    try:
        if request.method == 'DELETE':
            servers.remove_server(server_id)
        else:
            servers.update_server(server_id, _payload())
    except ValueError as exc:
        return jsonify({'message': str(exc)}), 400
    except OSError:
        return jsonify({'message': 'Could not update the secure credential store.'}), 500
    plexapi.plex_listener()
    return jsonify({'message': 'Server removed.' if request.method == 'DELETE' else 'Server settings saved.'})


def _refresh():
    """Dispatch one guarded dashboard refresh.

    Returns
    -------
    Thread
        Thread carrying the refresh job identifier.
    """
    from themerr import cache, scheduled_tasks
    return scheduled_tasks.run_threaded(target=cache.cache_data, task_name='Dashboard refresh')


@blueprint.route('/api/tasks/refresh', methods=['POST'])
def refresh():
    """Queue a dashboard refresh and optional theme scan.

    Returns
    -------
    Response
        Dispatch confirmation; processing continues in the background.
    """
    from common import config
    from themerr import scheduled_tasks
    if _payload().get('scan'):
        if not config.CONFIG['Themerr']['BOOL_THEMERR_ENABLED']:
            return jsonify({'message': 'Enable theme updates in Settings before starting a scan.'}), 400
        scheduled_tasks.run_threaded(target=plexapi.scheduled_update, task_name='Theme scan and queue')
    job = _refresh()
    return jsonify({'message': 'Refreshing libraries. Follow progress in Activity.', 'job_id': job.job_id}), 202


@blueprint.route('/activity')
def activity():
    """Show real task state and actionable media failures.

    Returns
    -------
    str
        Activity page with job history and failure details.
    """
    from themerr import scheduled_tasks
    libraries, _, _ = dashboard()
    failures = [{
        'server': section['server_name'], 'library': section['title'], **item,
        'reason': item['error'] or (
            'TMDB ID unavailable. Review the item metadata in Plex.'
            if item['theme_status'] == 'unresolved' else 'The theme could not be added.'
        ),
    } for section in libraries.values() for item in section['items']
        if item['error'] or item['theme_status'] in ('failed', 'unresolved')]
    return render_template('activity.html', title='Activity', jobs=scheduled_tasks.job_history(),
                           failures=failures, queue_size=plexapi.q.qsize())


@blueprint.route('/api/tasks')
def task_status():
    """Return bounded job history for the activity view.

    Returns
    -------
    Response
        Recent tasks and current queued item count.
    """
    from themerr import scheduled_tasks
    return jsonify({'jobs': scheduled_tasks.job_history(), 'queue_size': plexapi.q.qsize()})
