"""Describe the existing browser API without changing its validation or authentication."""

# standard imports
import copy

# lib imports
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute


_STRING = {'type': 'string'}
_ADD_SERVER = 'server_ui.add_server'
_BODIES = {
    'browse_directories': ({'path': _STRING}, [], {'path': ''}),
    'server_ui.discover': ({'source': {'type': 'string', 'enum': ['account', 'local']}},
                           ['source'], {'source': 'account'}),
    _ADD_SERVER: ({'url': _STRING, 'resource_id': _STRING}, [], {'url': 'http://127.0.0.1:32400'}),
    'server_ui.edit_server': ({'enabled': {'type': 'boolean'}, 'data_directory': _STRING,
                              'ignored_libraries': _STRING}, [], {'enabled': True}),
    'server_ui.refresh': ({'scan': {'type': 'boolean'}}, [], {'scan': False}),
    'admin.change_password': ({'current_password': _STRING, 'password': _STRING, 'confirm_password': _STRING},
                              ['current_password', 'password', 'confirm_password'], None),
}


def _documented_routes(routes: list) -> list:
    """Copy the public API routes into one documented operation per method."""
    documented = []
    for route in routes:
        if not isinstance(route, APIRoute) or not (route.path.startswith('/api/') or route.path == '/status'):
            continue
        if route.path in ('/api/docs', '/api/openapi.json'):
            continue
        for method in sorted(route.methods - {'HEAD'}):
            operation = copy.copy(route)
            operation.methods = {method}
            operation.unique_id = f'{route.name.replace(".", "_")}_{method.lower()}'
            docstring = (route.endpoint.__doc__ or '').strip()
            operation.summary = route.summary or docstring.split('\n')[0]
            documented.append(operation)
    return documented


def _request_body(name: str) -> dict | None:
    """Describe the form or JSON fields accepted by a POST operation."""
    if name == 'api_settings':
        return {
            'required': True, 'content': {'application/x-www-form-urlencoded': {'schema': {
                'type': 'object', 'additionalProperties': _STRING,
                'properties': {'General|LOCALE': _STRING},
                'description': 'Setting keys use Section|NAME; values are strings. Send only fields to change.',
            }, 'example': {'General|LOCALE': 'en'}}},
        }
    body = _BODIES.get(name)
    if body is None:
        return None
    properties, required, example = body
    media_type = 'application/x-www-form-urlencoded' if name == 'admin.change_password' else 'application/json'
    content = {'schema': {'type': 'object', 'properties': properties, 'required': required}}
    if example is not None:
        content['example'] = example
    return {'required': True, 'content': {media_type: content}}


def _describe_operation(route: APIRoute, operation: dict) -> None:
    """Add browser authentication, request bodies, and response metadata."""
    method = next(iter(route.methods)).lower()
    operation['responses']['200']['content'] = {'application/json': {'schema': {'type': 'object'}}}
    if route.name in (_ADD_SERVER, 'server_ui.refresh'):
        status = '201' if route.name == _ADD_SERVER else '202'
        operation['responses'][status] = operation['responses'].pop('200')
    operation['tags'] = [route.path.split('/')[2].title() if route.path.startswith('/api/') else 'Status']
    if route.path != '/status':
        operation['security'] = [{'BrowserSession': []}]
        operation['responses']['401'] = {'description': 'Sign in through the web interface.'}
    if method not in ('get', 'head'):
        operation.setdefault('parameters', []).append({
            'name': 'X-CSRFToken', 'in': 'header', 'required': True,
            'schema': _STRING, 'description': 'Signed token from the current page; filled in by this interface.',
        })
        operation['responses']['400'] = {'description': 'Invalid request body or missing/expired CSRF token.'}
    if method == 'post':
        body = _request_body(route.name)
        if body is not None:
            operation['requestBody'] = body
    if route.name.startswith('play_theme'):
        operation.setdefault('parameters', []).append({'name': 'Range', 'in': 'header', 'schema': _STRING})
        for status in ('200', '206'):
            operation['responses'][status] = {
                'description': 'Theme audio, optionally a byte range.',
                'content': {'audio/mpeg': {'schema': {'type': 'string', 'format': 'binary'}}},
            }
        operation['responses']['416'] = {'description': 'Requested audio range is unavailable.'}
    if route.name.startswith('theme_poster'):
        operation['responses']['200'] = {
            'description': 'Plex item poster.',
            'content': {kind: {'schema': {'type': 'string', 'format': 'binary'}}
                        for kind in ('image/jpeg', 'image/png', 'image/webp', 'image/gif')},
        }
        operation['responses']['404'] = {'description': 'Poster is unavailable.'}
        operation['responses']['502'] = {'description': 'Unable to load a bounded poster from Plex.'}


def schema(routes: list) -> dict:
    """Generate API operations from FastAPI routes, including browser request bodies.

    Parameters
    ----------
    routes : list
        Registered API and browser routes before inclusion in the application.

    Returns
    -------
    dict
        OpenAPI document with session authentication and CSRF requirements.

    Examples
    --------
    >>> document = schema(router.routes)
    """
    documented = _documented_routes(routes)
    document = get_openapi(
        title='Themerr-plex API', version='1', routes=documented,
        description='Sign in through the web interface to use these endpoints. The interactive documentation '
                    'uses your browser session and supplies its CSRF token for requests that change data.',
    )
    document.setdefault('components', {})['securitySchemes'] = {
        'BrowserSession': {'type': 'apiKey', 'in': 'cookie', 'name': 'session',
                           'description': 'Session cookie established by signing in through the web interface.'},
    }
    for route in documented:
        method = next(iter(route.methods)).lower()
        _describe_operation(route, document['paths'][route.path_format][method])
    return document
