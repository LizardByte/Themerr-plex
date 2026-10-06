"""Build the portable Jellyfin connector artifacts bundled with this Themerr build."""

# standard imports
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PROFILES = runpy.run_path(str(ROOT / 'src/jellyfin/compatibility.py'))['PROFILES']
PLUGIN_ID = 'f9a117dc-b44a-4507-9706-241837784369'
PLUGIN_NAME = 'Themerr Connector'
VERSION_FILE = 'src/common/version.py'
THUMBNAIL = 'thumb.png'
CONNECTOR_SOURCE = 'connectors/jellyfin'
ASSEMBLY_FILE = 'Themerr.Connector.dll'


def build_identity(root=ROOT, version=None):
    """Hash connector sources, compatibility profiles, and the Themerr release identity."""
    version = version or runpy.run_path(str(root / VERSION_FILE))['VERSION']
    digest = hashlib.sha256(version.encode())
    digest.update(json.dumps(PROFILES, sort_keys=True).encode())
    # Path ordering is case-insensitive on Windows and case-sensitive on POSIX.
    # Use the filename string so CI artifacts have the same identity on every host.
    for path in sorted((root / CONNECTOR_SOURCE).glob('*'), key=lambda source: source.name):
        if path.suffix in (
            '.cs',
            '.csproj',
            '.png',
        ):
            digest.update(path.name.encode())
            content = path.read_bytes()
            digest.update(content if path.suffix == '.png' else content.replace(b'\r\n', b'\n'))
    return digest.hexdigest()


def assembly_version(version):
    """Map timestamp release tags to four valid monotonic .NET version components."""
    parts = version.split('.')
    # release_setup strips leading zeroes from HHMMSS in its three-part scheme.
    # Its dotnet scheme instead emits HHMM and SS as separate integer components.
    if (
        len(parts) == 3
        and len(parts[0]) == 4
        and len(parts[1])
        in (
            3,
            4,
        )
        and parts[2].isascii()
        and parts[2].isdigit()
    ):
        timestamp = int(parts[2])
        parts = [
            parts[0],
            parts[1],
            str(timestamp // 100),
            str(timestamp % 100),
        ]
    parts += ['0'] * (4 - len(parts))
    if len(parts) != 4 or any(not p.isascii() or not p.isdigit() or int(p) > 65535 for p in parts):
        raise ValueError('Themerr release version must map to a valid four-part .NET version.')
    return '.'.join(str(int(p)) for p in parts)


def build(dotnet='dotnet', root=ROOT):
    """Compile every supported ABI and write fixed archive names and their checksums."""
    release = os.environ.get('THEMERR_VERSION') or runpy.run_path(str(root / VERSION_FILE))['VERSION']
    if os.environ.get('THEMERR_VERSION'):
        (root / VERSION_FILE).write_text(
            f'"""Release identity stamped by the release setup action."""\n\nVERSION = {release!r}\n', encoding='utf-8'
        )
    identity = build_identity(root, release)
    base_version = assembly_version(release)
    directory = root / 'jellyfin-connector'
    directory.mkdir(exist_ok=True)
    shutil.copyfile(root / CONNECTOR_SOURCE / THUMBNAIL, directory / THUMBNAIL)
    artifacts = {}
    for profile, values in PROFILES.items():
        abi = values['JellyfinMinimumVersion']
        version = base_version
        with tempfile.TemporaryDirectory(prefix='themerr-connector-') as temp:
            output = Path(temp) / 'out'
            subprocess.run(
                [
                    dotnet,
                    'build',
                    str(root / 'connectors/jellyfin/Themerr.Connector.csproj'),
                    '--configuration',
                    'Release',
                    '--output',
                    str(output),
                    '--configfile',
                    str(root / 'connectors/jellyfin/NuGet.Config'),
                    f'-p:JellyfinSeries={profile}',
                    f'-p:ConnectorBuild={identity}',
                    f'-p:AssemblyVersion={version}',
                    f'-p:BaseIntermediateOutputPath={Path(temp) / "obj"}{os.sep}',
                ],
                check=True,
            )
            archive = directory / values['ConnectorArchive']
            with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
                bundle.write(output / ASSEMBLY_FILE, ASSEMBLY_FILE)
            artifacts[profile] = {
                'targetAbi': abi,
                'version': version,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'checksum': hashlib.md5(archive.read_bytes(), usedforsecurity=False).hexdigest(),
            }
    descriptor = {
        'build': identity,
        'themerrVersion': release,
        'protocol': 1,
        'artifacts': artifacts,
    }
    (directory / 'bundle.json').write_text(f'{json.dumps(descriptor, indent=2)}\n', encoding='utf-8')
    return descriptor


def check_bundle(root=ROOT):
    """Validate reusable connector artifacts against source, release, ABI and archive checksums."""
    directory = root / 'jellyfin-connector'
    descriptor = json.loads((directory / 'bundle.json').read_text(encoding='utf-8'))
    release = os.environ.get('THEMERR_VERSION') or runpy.run_path(str(root / VERSION_FILE))['VERSION']
    if (
        descriptor.get('protocol') != 1
        or descriptor.get('build') != build_identity(root, release)
        or descriptor.get('themerrVersion') != release
        or set(descriptor['artifacts']) != set(PROFILES)
    ):
        raise ValueError('Prebuilt Jellyfin connector does not match this Themerr source and release.')
    if (directory / THUMBNAIL).read_bytes() != (root / CONNECTOR_SOURCE / THUMBNAIL).read_bytes():
        raise ValueError('Prebuilt Jellyfin connector thumbnail does not match.')
    for profile, values in PROFILES.items():
        artifact = descriptor['artifacts'][profile]
        archive = directory / values['ConnectorArchive']
        if (
            artifact['targetAbi'] != values['JellyfinMinimumVersion']
            or artifact['version'] != assembly_version(release)
            or artifact['checksum'] != hashlib.md5(archive.read_bytes(), usedforsecurity=False).hexdigest()
        ):
            raise ValueError('Prebuilt Jellyfin connector checksum or ABI does not match.')
        with zipfile.ZipFile(archive) as content:
            if content.namelist() != [ASSEMBLY_FILE]:
                raise ValueError('Prebuilt Jellyfin connector contains unexpected files.')
    return descriptor


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dotnet', default='dotnet')
    parser.add_argument('--check', action='store_true', help='Validate existing artifacts without using .NET.')
    arguments = parser.parse_args()
    check_bundle() if arguments.check else build(arguments.dotnet)
