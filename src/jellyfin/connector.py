"""Serve and install only connector artifacts bundled with this Themerr release."""

import json
from pathlib import Path
from threading import RLock
from urllib.parse import quote

import requests

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
PROFILE_MANIFESTS = {'10.11': '/jellyfin/connector/manifest-10.11.json',
                     '12.1': '/jellyfin/connector/manifest-12.1.json'}
THUMBNAIL_PATH = '/jellyfin/connector/thumb.png'
PUBLIC_PATHS = frozenset([MANIFEST_PATH, THUMBNAIL_PATH, *PROFILE_MANIFESTS.values(),
                          *('/jellyfin/connector/' + name for name in ARCHIVES.values())])
_install_lock = RLock()
LEGACY_PLUGIN_ID = 'e41ef0c4-c413-41ba-b4fa-8c565dc3c969'
LEGACY_REPOSITORY = 'https://app.lizardbyte.dev/jellyfin-plugin-repo/manifest.json'
_REPOSITORIES = '/Repositories'


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


def repository_url(value=None, required=True):
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
            if not required:
                return None
            raise MediaServerError('Set the Themerr address reachable from Jellyfin '
                                   'before installing the connector.', 409)
        return row.value


def manifest(profile_key=None):
    """Advertise exactly the locally bundled versions using the configured download address."""
    data = bundle()
    url = repository_url()
    return [{'guid': PLUGIN_ID, 'name': PLUGIN_NAME, 'overview': 'Theme uploads for the matching Themerr build.',
             'description': 'Managed by your Themerr installation. Restart Jellyfin after installation.',
             'owner': 'LizardByte', 'category': 'General', 'imageUrl': url + THUMBNAIL_PATH,
             'versions': [{**artifact, 'sourceUrl': url + '/jellyfin/connector/' + ARCHIVES[key],
                           'changelog': 'Connector bundled with Themerr ' + data['themerrVersion']}
                          for key, artifact in data['artifacts'].items() if profile_key is None or key == profile_key]}]


def configure_repository(value):
    """Validate and persist an administrator-selected address without installing a package."""
    url = base_url(value)
    _check_certificate(url)
    return repository_url(url)


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
    manifest_path = PROFILE_MANIFESTS[key]
    manifest_url = url + manifest_path
    with _install_lock:
        try:
            verify(connection)
            active = True
        except MediaServerError:
            active = False
        _register_repository(connection, url, manifest_url)
        if active:
            return {'message': 'Matching connector is already active.', 'version': artifact['version'],
                    'restart_required': False}
        _check_repository(connection, url, artifact, manifest_path)
        pending, replace_loaded = _prepare_installation(connection, artifact['version'])
        if replace_loaded:
            return {'message': 'Jellyfin must restart before replacing the connector.',
                    'version': artifact['version'], 'restart_required': True, 'reinstall_required': True}
        if not pending:
            connection.request('POST', '/Packages/Installed/' + PLUGIN_NAME,
                               params={'assemblyGuid': PLUGIN_ID, 'version': artifact['version'],
                                       'repositoryUrl': manifest_url}, timeout=120).close()
    return {'message': 'Connector installed. Jellyfin must restart to load it.',
            'version': artifact['version'], 'restart_required': True}


def _register_repository(connection, url, manifest_url):
    """Merge Jellyfin's replacement repository list without changing unrelated entries."""
    repositories = connection.json('GET', _REPOSITORIES)
    if not isinstance(repositories, list) or any(not isinstance(entry, dict) for entry in repositories):
        raise MediaServerError('Jellyfin returned an invalid repository list.', 502)
    owned_repositories = {url + path for path in (MANIFEST_PATH, *PROFILE_MANIFESTS.values())}
    repositories = [entry for entry in repositories if entry.get('Url') not in owned_repositories]
    repositories.append({'Name': PLUGIN_NAME, 'Url': manifest_url, 'Enabled': True})
    _check_certificate(url)
    repository_url(url)
    connection.request('POST', _REPOSITORIES, json=repositories).close()


def _prepare_installation(connection, version):
    """Preserve pending installs and remove only this connector's older loaded assemblies."""
    plugins = connection.json('GET', '/Plugins')
    if not isinstance(plugins, list) or any(not isinstance(plugin, dict) for plugin in plugins):
        raise MediaServerError('Jellyfin returned an invalid plugin list.', 502)
    owned = [plugin for plugin in plugins
             if str(plugin.get('Id', '')).replace('-', '').lower() == PLUGIN_ID.replace('-', '')]
    pending = any(plugin.get('Version') == version and plugin.get('Status') == 'Restart' for plugin in owned)
    if pending:
        return True, False
    replace_loaded = False
    for plugin in owned:
        plugin_version = str(plugin.get('Version', ''))
        parts = plugin_version.split('.')
        if len(parts) != 4 or not all(part.isascii() and part.isdigit() for part in parts):
            raise MediaServerError('Jellyfin returned an invalid connector version.', 502)
        if plugin.get('Status') != 'Deleted':
            connection.request('DELETE', '/Plugins/' + PLUGIN_ID + '/' + quote(plugin_version, safe='')).close()
        # On Windows a loaded DLL cannot be overwritten; unload changed builds of the same version first.
        replace_loaded = replace_loaded or plugin_version == version
    return False, replace_loaded


def _check_certificate(url):
    """Reject untrusted HTTPS before storing or registering a repository address."""
    if url.startswith('https:'):
        try:
            # No credentials are sent to this administrator-selected repository URL.
            # CodeQL py/full-ssrf: authenticated admins choose their reachable Themerr repository.
            # base_url restricts URL syntax and schemes; LAN/loopback deployments are intentional.
            # Probe only this fixed manifest, with TLS validation, no credentials and no redirects.
            response = requests.get(url + MANIFEST_PATH, timeout=10, allow_redirects=False, stream=True)
            response.close()
        except requests.exceptions.SSLError as exc:
            raise MediaServerError('Themerr’s HTTPS certificate is not trusted or does not match its address. '
                                   'Use the connector-only HTTP port or a trusted HTTPS address.', 400) from exc
        except requests.RequestException as exc:
            raise MediaServerError('Could not reach the Themerr repository address. Check its host and port.',
                                   502) from exc


def _check_repository(connection, url, artifact, manifest_path=MANIFEST_PATH):
    """Prove that Jellyfin can fetch the matching package before requesting installation."""
    try:
        package = connection.json('GET', '/Packages/' + PLUGIN_NAME, params={'assemblyGuid': PLUGIN_ID}, timeout=120)
    except MediaServerError as exc:
        if exc.status_code != 404:
            raise
        raise MediaServerError('Jellyfin could not read the Themerr connector repository. Check the reachable '
                               'address, port and firewall. HTTPS requires a certificate Jellyfin trusts; '
                               'use the connector-only HTTP port for self-signed certificates.', 502) from exc
    versions = package.get('versions', package.get('Versions', [])) if isinstance(package, dict) else []
    if not isinstance(versions, list) or not any(
            isinstance(entry, dict) and entry.get('version', entry.get('Version')) == artifact['version'] and
            entry.get('repositoryUrl', entry.get('RepositoryUrl')) == url + manifest_path for entry in versions):
        raise MediaServerError('Jellyfin did not find the matching connector in this repository. '
                               'Check the Themerr address and rebuild or reinstall Themerr.', 502)


def remove_legacy(connection):
    """Uninstall only the known legacy plugin and its exact dedicated repository."""
    changed = False
    plugins = connection.json('GET', '/Plugins')
    if not isinstance(plugins, list) or any(not isinstance(plugin, dict) for plugin in plugins):
        raise MediaServerError('Jellyfin returned an invalid plugin list.', 502)
    for plugin in plugins:
        if (str(plugin.get('Id', '')).replace('-', '').lower() == LEGACY_PLUGIN_ID.replace('-', '') and
                plugin.get('Status') != 'Deleted'):
            version = str(plugin.get('Version', ''))
            parts = version.split('.')
            if len(parts) != 4 or not all(part.isascii() and part.isdigit() for part in parts):
                raise MediaServerError('Jellyfin returned an invalid legacy plugin version.', 502)
            connection.request('DELETE', '/Plugins/' + LEGACY_PLUGIN_ID + '/' + quote(version, safe='')).close()
            changed = True
    repositories = connection.json('GET', _REPOSITORIES)
    if not isinstance(repositories, list) or any(not isinstance(entry, dict) for entry in repositories):
        raise MediaServerError('Jellyfin returned an invalid repository list.', 502)
    remaining = [entry for entry in repositories if entry.get('Url', '').rstrip('/') != LEGACY_REPOSITORY]
    if len(remaining) != len(repositories):
        connection.request('POST', _REPOSITORIES, json=remaining).close()
    return changed
