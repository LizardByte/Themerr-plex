"""Serve and install only connector artifacts bundled with this Themerr release."""

import json
from pathlib import Path
from threading import RLock

from sqlalchemy.orm import Session

from common import definitions, version
from common.path_policy import resolve_file_path
from jellyfin.client import base_url
from media_servers.base import MediaServerError
from themerr import storage

PLUGIN_ID = 'f9a117dc-b44a-4507-9706-241837784369'
PLUGIN_NAME = 'Themerr Connector'
ARCHIVES = {'10.11': 'connector-10.11.zip', '12.1': 'connector-12.1.zip'}
MANIFEST_PATH = '/jellyfin/connector/manifest.json'
PUBLIC_PATHS = frozenset([MANIFEST_PATH, *('/jellyfin/connector/' + name for name in ARCHIVES.values())])
_install_lock = RLock()


def directory():
    """Locate immutable connector data in source, Docker, or PyInstaller resources."""
    return Path(definitions.Paths.ROOT_DIR) / 'jellyfin-connector'


def bundle():
    """Read the packaged descriptor through the shared canonical containment policy."""
    try:
        path = resolve_file_path(directory(), 'bundle.json')
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if data['protocol'] != 1 or data['themerrVersion'] != version.VERSION:
            raise ValueError
        if set(data['artifacts']) != set(ARCHIVES) or len(data['build']) != 64:
            raise ValueError
        return data
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise MediaServerError('The bundled Jellyfin connector is unavailable. '
                               'Rebuild or reinstall Themerr.', 503) from exc


def profile(server_version):
    """Select an explicitly supported Jellyfin minor version instead of guessing ABI compatibility."""
    key = '.'.join(str(server_version).split('.')[:2])
    if key not in ARCHIVES:
        raise MediaServerError('This build supports Jellyfin 10.11 and 12.1.', 400)
    return key


def repository_url(value=None):
    """Save or read the administrator-selected Themerr URL reachable from Jellyfin."""
    with Session(storage.engine()) as session:
        row = session.get(storage.AppSetting, 'jellyfin_repository_base_url')
        if value is not None:
            value = base_url(value)
            if row is None:
                row = storage.AppSetting(key='jellyfin_repository_base_url', value=value)
                session.add(row)
            else:
                row.value = value
            session.commit()
            return value
        if row is None:
            raise MediaServerError('Set the Themerr address reachable from Jellyfin '
                                   'before installing the connector.', 409)
        return row.value


def manifest():
    """Advertise exactly the locally bundled versions using the configured download address."""
    data = bundle()
    url = repository_url()
    return [{'guid': PLUGIN_ID, 'name': PLUGIN_NAME, 'overview': 'Theme uploads for the matching Themerr build.',
             'description': 'Managed by your Themerr installation. Restart Jellyfin after installation.',
             'owner': 'LizardByte', 'category': 'General',
             'versions': [{**artifact, 'sourceUrl': url + '/jellyfin/connector/' + ARCHIVES[key],
                           'changelog': 'Connector bundled with Themerr ' + data['themerrVersion']}
                          for key, artifact in data['artifacts'].items()]}]


def verify(connection):
    """Require the exact connector identity and protocol before accessing theme operations."""
    expected = bundle()
    artifact = expected['artifacts'][profile(connection.server_version)]
    try:
        actual = connection.json('GET', '/Themerr/Connector')
    except MediaServerError as exc:
        raise MediaServerError('Install the matching Themerr connector and restart Jellyfin.', 409) from exc
    if (not isinstance(actual, dict) or actual.get('protocol') != expected['protocol'] or
            actual.get('build') != expected['build'] or actual.get('targetAbi') != artifact['targetAbi']):
        raise MediaServerError('Install the matching Themerr connector and restart Jellyfin.', 409)
    return expected


def install(connection, themerr_url):
    """Preserve existing repositories and request the exact bundled compatible plugin version."""
    data = bundle()
    info = connection.json('GET', '/System/Info')
    key = profile(info.get('Version'))
    artifact = data['artifacts'][key]
    url = base_url(themerr_url)
    manifest_url = url + MANIFEST_PATH
    with _install_lock:
        try:
            verify(connection)
            active = True
        except MediaServerError:
            active = False
        # Jellyfin replaces the repository list, so merge instead of overwriting it.
        repositories = connection.json('GET', '/Repositories')
        if not isinstance(repositories, list) or any(not isinstance(entry, dict) for entry in repositories):
            raise MediaServerError('Jellyfin returned an invalid repository list.', 502)
        repositories = [entry for entry in repositories if entry.get('Url') != manifest_url]
        repositories.append({'Name': PLUGIN_NAME + ' (Themerr)', 'Url': manifest_url, 'Enabled': True})
        repository_url(url)
        connection.request('POST', '/Repositories', json=repositories).close()
        if active:
            return {'message': 'Matching connector is already active.', 'version': artifact['version'],
                    'restart_required': False}
        connection.request('POST', '/Packages/Installed/' + PLUGIN_NAME,
                           params={'assemblyGuid': PLUGIN_ID, 'version': artifact['version'],
                                   'repositoryUrl': manifest_url}, timeout=120).close()
    return {'message': 'Connector installed. Restart Jellyfin, then refresh its libraries in Themerr.',
            'version': artifact['version'], 'restart_required': True}
