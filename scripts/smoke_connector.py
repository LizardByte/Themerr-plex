"""Install the same bundled connector on each series' minimum and latest official Jellyfin image."""

# standard imports
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from threading import Thread
import time
from unittest.mock import patch
from uuid import uuid4

# lib imports
import requests
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

# local imports
from build_connector import check_bundle  # noqa: E402 - standalone script imports
from jellyfin import connector, repository  # noqa: E402
from jellyfin.client import Client  # noqa: E402
from jellyfin.compatibility import PROFILES, version_parts  # noqa: E402


def docker(*arguments):
    """Run a Docker command without a shell and retain diagnostics for failures."""
    result = subprocess.run(
        [
            'docker',
            *arguments,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def wait_for(callback, description, timeout=180):
    """Wait for an isolated server operation without hiding its eventual failure."""
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            value = callback()
            if value:
                return value
        except requests.RequestException as exc:
            last_error = exc
        time.sleep(1)
    raise RuntimeError(f'Timed out waiting for {description}.') from last_error


def request(url, method, path, **kwargs):
    """Use fixed startup and authentication routes on the local test server."""
    response = requests.request(method, f'{url}{path}', timeout=30, **kwargs)
    response.raise_for_status()
    return response.json() if response.content else None


def setup(url):
    """Finish the startup wizard using credentials confined to a disposable server."""
    request(
        url,
        'POST',
        '/Startup/Configuration',
        json={
            'UICulture': 'en-US',
            'MetadataCountryCode': 'US',
            'PreferredMetadataLanguage': 'en',
        },
    )
    request(url, 'GET', '/Startup/User')
    password = uuid4().hex
    request(url, 'POST', '/Startup/User', json={
        'Name': 'themerr-validation',
        'Password': password,
    })
    request(
        url,
        'POST',
        '/Startup/RemoteAccess',
        json={
            'EnableRemoteAccess': True,
            'EnableAutomaticPortMapping': False,
        },
    )
    request(url, 'POST', '/Startup/Complete')
    authentication = request(
        url,
        'POST',
        '/Users/AuthenticateByName',
        json={
            'Username': 'themerr-validation',
            'Pw': password,
        },
        headers={
            'Authorization': 'MediaBrowser Client="Themerr Validation", Device="Smoke", '
                             'DeviceId="themerr-validation", Version="1"',
            'Accept': 'application/json; profile="PascalCase"',
        },
    )
    connection = Client(url, authentication['AccessToken'])
    connection.request('POST', '/Auth/Keys', params={'app': 'Themerr Validation'}).close()
    keys = connection.json('GET', '/Auth/Keys')['Items']
    connection = Client(url, next(key['AccessToken'] for key in keys if key['AppName'] == 'Themerr Validation'))
    connection.json('GET', '/System/Info')
    return connection


def server_url(name):
    """Read the disposable container's currently assigned loopback port."""
    binding = json.loads(docker('inspect', name))[0]['NetworkSettings']['Ports']['8096/tcp'][0]
    return f'http://127.0.0.1:{binding["HostPort"]}'


def restart(name, connection):
    """Restart the disposable container and wait for the connector to become usable."""
    docker('restart', name)
    connection.url = server_url(name)

    def ready():
        response = requests.get(
            f'{connection.url}/Themerr/Connector',
            headers={'Authorization': f'MediaBrowser Token="{connection.token}"'},
            timeout=5,
        )
        response.raise_for_status()
        return True

    wait_for(ready, 'Jellyfin restart')
    connection.json('GET', '/System/Info')
    connector.verify(connection)


def validate(name, tag, media, repository_url):
    """Exercise installation, uploads, EF ownership persistence, and protected user themes."""
    url = server_url(name)
    wait_for(lambda: request(url, 'GET', '/System/Info/Public'), f'Jellyfin {tag} startup')
    wait_for(lambda: request(url, 'GET', '/Startup/Configuration'), f'Jellyfin {tag} wizard readiness')
    connection = setup(url)
    if version_parts(connection.server_version) != version_parts(tag):
        raise RuntimeError('The running server does not match the requested validation version.')
    result = connector.install(connection, repository_url)
    if not result['restart_required']:
        raise RuntimeError('The fresh test server did not install its connector.')
    restart(name, connection)
    if connector.install(connection, repository_url)['restart_required']:
        raise RuntimeError('The active matching connector requested an unnecessary reinstall.')

    ffmpeg = '/usr/lib/jellyfin-ffmpeg/ffmpeg'
    docker(
        'exec', name, ffmpeg, '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
        'color=black:s=320x240:r=1', '-t', '1', '-c:v', 'mpeg4', '/media/Example/Example.mp4',
    )
    docker(
        'exec', name, ffmpeg, '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
        'sine=frequency=440:duration=1', '-c:a', 'aac', '/media/upload.m4a',
    )
    connection.request(
        'POST',
        '/Library/VirtualFolders',
        params={
            'name': 'Validation',
            'collectionType': 'movies',
            'refreshLibrary': True,
        },
        json={
            'LibraryOptions': {
                'PathInfos': [{'Path': '/media'}],
                'EnableRealtimeMonitor': False,
                'EnableInternetProviders': False,
                'TypeOptions': [{
                    'Type': 'Movie',
                    'MetadataFetchers': [],
                    'ImageFetchers': [],
                }],
            },
        },
    ).close()

    def movie():
        items = connection.json(
            'GET', '/Items', params={
                'Recursive': True,
                'IncludeItemTypes': 'Movie',
            },
        )['Items']
        return next((item['Id'] for item in items if item['Name'] == 'Example'), None)

    item_id = wait_for(movie, 'test library scan')
    route = f'/Themerr/Items/{item_id}/Theme'
    audio = (media / 'upload.m4a').read_bytes()
    digest = hashlib.sha256(audio).hexdigest()
    state = connection.json(
        'POST',
        route,
        data=audio,
        headers={
            'Content-Type': 'audio/mp4',
            'X-Themerr-Connector': connector.bundle()['build'],
            'X-Themerr-SHA256': digest,
        },
    )
    if not state['owned'] or state['sha256'] != digest:
        raise RuntimeError('Theme upload did not establish ownership.')
    restart(name, connection)
    if not connection.json('GET', route)['owned']:
        raise RuntimeError('Theme ownership was not preserved across a restart.')
    theme = media / 'Example/theme.m4a'
    if theme.read_bytes() != audio:
        raise RuntimeError('The theme file does not match the uploaded audio.')
    theme.write_bytes(b'changed by user')
    if connection.json('GET', route)['owned']:
        raise RuntimeError('A user-modified theme retained connector ownership.')
    response = requests.post(
        f'{connection.url}{route}',
        data=audio,
        headers={
            'Authorization': f'MediaBrowser Token="{connection.token}"',
            'Content-Type': 'audio/mp4',
            'X-Themerr-Connector': connector.bundle()['build'],
            'X-Themerr-SHA256': digest,
        },
        timeout=30,
    )
    if response.status_code != 409 or theme.read_bytes() != b'changed by user':
        raise RuntimeError('The connector did not protect a user-modified theme.')
    print(f'PASS Jellyfin {tag}: install, restart, identity, upload, ownership persistence, user-theme protection.',
          flush=True)


def smoke(series=None):
    """Start a repository listener and clean up only containers created by this validation run."""
    check_bundle()
    with socket.socket() as listener:
        listener.bind(('0.0.0.0', 0))
        port = listener.getsockname()[1]
    repository_url = f'http://host.docker.internal:{port}'
    server = uvicorn.Server(uvicorn.Config(
        repository.create_app(), host='0.0.0.0', port=port, log_level='warning',
    ))
    thread = Thread(target=server.run, daemon=True)
    with patch.object(connector, 'repository_url', return_value=repository_url):
        thread.start()
        try:
            wait_for(lambda: server.started, 'connector repository startup', timeout=30)
            for key, values in PROFILES.items():
                if series and key not in series:
                    continue
                minimum = values['JellyfinMinimumVersion']
                if version_parts(minimum)[0] >= 12:
                    minimum = minimum.removesuffix('.0')
                for tag in dict.fromkeys([
                    minimum,
                    values['JellyfinLatestVersion'],
                ]):
                    print(f'Validating Jellyfin {tag} using the {key} series artifact...', flush=True)
                    name = f'themerr-connector-smoke-{uuid4().hex[:12]}'
                    with tempfile.TemporaryDirectory(prefix='themerr-connector-smoke-') as temporary:
                        root = Path(temporary)
                        config = root / 'config'
                        cache = root / 'cache'
                        media = root / 'media'
                        config.mkdir()
                        cache.mkdir()
                        (media / 'Example').mkdir(parents=True)
                        # Keep Linux bind mounts owned by the caller so temporary files can be removed.
                        user = [
                            '--user',
                            f'{os.getuid()}:{os.getgid()}',
                        ] if hasattr(os, 'getuid') else []
                        created = False
                        try:
                            docker(
                                'run', '--detach', '--name', name, '--publish', '127.0.0.1::8096',
                                *user,
                                '--add-host', 'host.docker.internal:host-gateway',
                                '--mount', f'type=bind,source={config},target=/config',
                                '--mount', f'type=bind,source={cache},target=/cache',
                                '--mount', f'type=bind,source={media},target=/media',
                                f'jellyfin/jellyfin:{tag}',
                            )
                            created = True
                            validate(name, tag, media, repository_url)
                        except Exception:
                            if created:
                                print(docker('logs', '--tail', '80', name), file=sys.stderr)
                            raise
                        finally:
                            if created:
                                docker('rm', '--force', '--volumes', name)
        finally:
            server.should_exit = True
            thread.join(timeout=15)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--series', action='append', choices=PROFILES, help='Validate only the selected series.')
    arguments = parser.parse_args()
    smoke(arguments.series)
