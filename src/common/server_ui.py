"""Authenticated server management, discovery, and dashboard views."""

# standard imports
import re
from urllib.parse import quote, urlencode

# lib imports
from fastapi import APIRouter, Depends, Request
from starlette.responses import JSONResponse
from fastapi import HTTPException
from plexapi.exceptions import Unauthorized
from requests.exceptions import ConnectionError, RequestException, SSLError, Timeout

# local imports
from common.http import read_json, render_template
from common import logger
from common.validation import ValidationError
from plex import auth, plexapi, servers, token_store
from themerr import storage, theme_errors

router = APIRouter()
log = logger.get_logger(__name__)


def _failure(error: Exception, message: str, status: int = 502):
    """Report the failure category without exposing upstream tokens or response bodies.

    Parameters
    ----------
    error : Exception
        Original failure; only its class name is logged.
    message : str
        Safe explanation for the administrator.
    status : int, optional
        HTTP response status.

    Returns
    -------
    JSONResponse
        JSON response with the requested status code.
    """
    log.warning('%s (%s)', message, type(error).__name__)
    return JSONResponse({'message': message}, status_code=status)


async def _payload(request: Request) -> dict:
    """Reject JSON arrays and scalar values at the API boundary."""
    payload = await read_json(request)
    return _validated_payload(payload)


def _validated_payload(payload) -> dict:
    """Require an object before passing submitted preferences to the server store."""
    if not isinstance(payload, dict):
        raise HTTPException(400, 'Invalid JSON object.')
    return payload


def _metadata_url(item: dict) -> str | None:
    """Link validated external IDs to their metadata provider.

    Parameters
    ----------
    item : dict
        Cached Plex item and resolved external identifiers.

    Returns
    -------
    str or None
        Provider URL when the ID and media type are supported.
    """
    identifier = str(item.get('database_id') or item.get('source_id') or '')
    database = item.get('source_database')
    if item.get('database_id'):
        database = 'imdb' if identifier.startswith('tt') else 'themoviedb'
    if database == 'imdb' and re.fullmatch(r'tt\d+', identifier):
        return 'https://www.imdb.com/title/' + identifier + '/'
    if not identifier.isascii() or not identifier.isdigit():
        return None
    if database == 'themoviedb':
        category = {'movie': 'movie', 'show': 'tv', 'collection': 'collection'}.get(item.get('type'))
        return 'https://www.themoviedb.org/' + category + '/' + identifier if category else None
    if database == 'thetvdb' and item.get('type') == 'show':
        return 'https://thetvdb.com/dereferrer/series/' + identifier
    return None


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
            server_url = ('https://app.plex.tv/desktop/#!/media/' + quote(record['id'], safe='') +
                          '/com.plexapp.plugins.library')
            libraries[identity] = {**section, 'server_id': record['id'], 'server_name': record['name'],
                                   'enabled': record['enabled'], 'server_url': server_url,
                                   'library_url': server_url + '?' + urlencode({'source': section['key']})}
            for item in section['items']:
                item['server_id'] = record['id']
                item['error'] = failures.get(item['rating_key'])
                item['plex_url'] = 'https://app.plex.tv/desktop/#!/server/' + quote(record['id'], safe='') + (
                    '/details?' + urlencode({'key': '/library/metadata/' + str(item['rating_key'])}))
                item['metadata_url'] = _metadata_url(item)
                item['show_edit'] = theme_errors.is_video_issue(item['error'])
                errors[record['id'] + ':' + item['rating_key']] = item['error']
    items = [item for section in libraries.values() for item in section['items']]
    installed = sum(item['theme'] for item in items)
    return libraries, errors, {'total': len(items), 'installed': installed,
                               'coverage': round(installed / len(items) * 100) if items else 0,
                               'attention': sum(bool(item['error']) or item['theme_status'] in ('failed', 'unresolved')
                                                for item in items), 'servers': len(registered),
                               'libraries': len(libraries)}


@router.api_route('/servers', methods=['GET', 'HEAD'], name='server_ui.server_page', response_model=None)
def server_page(request: Request):
    """Render saved connections and discovery options.

    Returns
    -------
    str
        Server management page.
    """
    return render_template(
        request,
        'servers.html',
        title='Servers',
        servers=servers.list_servers(),
        plex_connected=bool(auth.get_token()),
    )


@router.api_route('/api/servers/discover', methods=['POST'], name='server_ui.discover', response_model=None)
def discover(payload=Depends(_payload)):
    """List account or LAN resources without disclosing access tokens.

    Returns
    -------
    Response
        Safe discovery results or a connection error.
    """
    source = payload.get('source')
    if source not in ('account', 'local'):
        return JSONResponse({'message': 'Choose account or local discovery.'}, status_code=400)
    try:
        resources = servers.discover_account() if source == 'account' else servers.discover_local()
    except Exception as exc:
        return _failure(exc, 'Discovery failed. Check the Plex connection, or enter an address manually.')
    return JSONResponse({'servers': resources})


@router.api_route('/api/servers', methods=['POST'], name='server_ui.add_server', response_model=None)
def add_server(payload=Depends(_payload)):
    """Connect to a selected or manually addressed server.

    Returns
    -------
    Response
        Saved public settings or a sanitized failure.
    """
    try:
        record = servers.add_server(payload.get('url', ''), payload.get('resource_id'))
    except token_store.TokenStorageError as exc:
        return _failure(exc, 'Unable to save the Plex token. Check the configured credential store.', 500)
    except SSLError as exc:
        return _failure(exc, 'The secure connection to Plex failed. Use its advertised HTTPS address and check '
                        'the server certificate.')
    except Timeout as exc:
        return _failure(exc, 'The Plex connection timed out. Check that the server is running and this address is '
                        'reachable from the machine running Themerr. Try another advertised or manual address.')
    except ConnectionError as exc:
        return _failure(exc, 'Could not connect to this Plex address. Check its hostname, port, and network access '
                        'from the machine running Themerr, or try another address.')
    except Unauthorized as exc:
        return _failure(exc, 'Plex denied access to this server. Check the linked account has permission, or '
                        'reconnect your Plex account.')
    except RequestException as exc:
        return _failure(exc, 'Plex returned an invalid response. Check the address or try another connection.')
    except ValidationError as exc:
        return _failure(exc, exc.reason.value, 400)
    except Exception as exc:
        return _failure(exc, 'Could not connect to this Plex server. Check the address and account access.')
    plexapi.plex_listener()
    _refresh()
    return JSONResponse({'server': record}, status_code=201)


@router.api_route(
    '/api/servers/{server_id}',
    methods=['POST', 'DELETE'],
    name='server_ui.edit_server',
    response_model=None,
)
def edit_server(request: Request, server_id: str, payload=Depends(read_json)):
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
        return JSONResponse({'message': 'Server not found.'}, status_code=404)
    if request.method != 'DELETE':
        payload = _validated_payload(payload)
    try:
        if request.method == 'DELETE':
            servers.remove_server(server_id)
        else:
            servers.update_server(server_id, payload)
    except ValidationError as exc:
        return _failure(exc, exc.reason.value, 400)
    except token_store.TokenStorageError as exc:
        return _failure(exc, 'Could not update the secure credential store.', 500)
    except Exception as exc:
        return _failure(exc, 'Could not update this Plex server. Check its connection and settings.', 500)
    plexapi.plex_listener()
    return JSONResponse({'message': 'Server removed.' if request.method == 'DELETE' else 'Server settings saved.'})


def _refresh():
    """Dispatch one guarded dashboard refresh.

    Returns
    -------
    Thread
        Thread carrying the refresh job identifier.
    """
    from themerr import cache, scheduled_tasks
    return scheduled_tasks.run_threaded(target=cache.cache_data, task_name='Dashboard refresh')


@router.api_route('/api/tasks/refresh', methods=['POST'], name='server_ui.refresh', response_model=None)
def refresh(payload=Depends(_payload)):
    """Queue a dashboard refresh and optional theme scan.

    Returns
    -------
    Response
        Dispatch confirmation; processing continues in the background.
    """
    from common import config
    from themerr import scheduled_tasks
    if payload.get('scan'):
        if not config.CONFIG['Themerr']['BOOL_THEMERR_ENABLED']:
            return JSONResponse(
                {'message': 'Enable theme updates in Settings before starting a scan.'},
                status_code=400,
            )
        scheduled_tasks.run_threaded(target=plexapi.scheduled_update, task_name='Theme scan and queue')
    job = _refresh()
    return JSONResponse(
        {'message': 'Refreshing libraries. Follow progress in Activity.', 'job_id': job.job_id},
        status_code=202,
    )


@router.api_route('/api/themerrdb', methods=['GET', 'HEAD'], name='server_ui.database_status', response_model=None)
def database_status():
    """Return the latest successful ThemerrDB Pages deployment from the hourly cache.

    Returns
    -------
    Response
        Deployment metadata and check timestamps.
    """
    from themerr import github_status
    return JSONResponse(github_status.publication_status())


@router.api_route('/activity', methods=['GET', 'HEAD'], name='server_ui.activity', response_model=None)
def activity(request: Request):
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
    return render_template(
        request,
        'activity.html',
        title='Activity',
        jobs=scheduled_tasks.job_history(),
        failures=failures,
        queue_size=plexapi.q.qsize(),
    )


@router.api_route('/api/tasks', methods=['GET', 'HEAD'], name='server_ui.task_status', response_model=None)
def task_status():
    """Return bounded job history for the activity view.

    Returns
    -------
    Response
        Recent tasks and current queued item count.
    """
    from themerr import scheduled_tasks
    return JSONResponse({'jobs': scheduled_tasks.job_history(), 'queue_size': plexapi.q.qsize()})
