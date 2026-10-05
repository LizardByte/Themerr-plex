"""Build the portable Jellyfin connector artifacts bundled with this Themerr build."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PROFILES = {'10.11': ('10.11.0', 'net9.0'), '12.1': ('12.1.0', 'net10.0')}
PLUGIN_ID = 'f9a117dc-b44a-4507-9706-241837784369'
PLUGIN_NAME = 'Themerr Connector'


def build_identity(root=ROOT, version=None):
    """Hash connector sources, compatibility profiles, and the Themerr release identity."""
    version = version or runpy.run_path(str(root / 'src/common/version.py'))['VERSION']
    digest = hashlib.sha256(version.encode())
    digest.update(json.dumps(PROFILES, sort_keys=True).encode())
    for path in sorted((root / 'connectors/jellyfin').glob('*')):
        if path.suffix in ('.cs', '.csproj'):
            digest.update(path.name.encode())
            digest.update(path.read_bytes().replace(b'\r\n', b'\n'))
    return digest.hexdigest()


def assembly_version(version):
    """Map timestamp release tags to four valid monotonic .NET version components."""
    if version == '0.0.0':
        now = datetime.now(timezone.utc)
        return f'{now.year}.{now.month * 100 + now.day}.{now.hour * 100 + now.minute}.{now.second}'
    parts = version.split('.')
    if len(parts) == 3 and len(parts[2]) == 6:
        parts = [parts[0], parts[1], str(int(parts[2][:4])), str(int(parts[2][4:]))]
    parts += ['0'] * (4 - len(parts))
    if len(parts) != 4 or any(not p.isascii() or not p.isdigit() or int(p) > 65535 for p in parts):
        raise ValueError('Themerr release version must map to a valid four-part .NET version.')
    return '.'.join(str(int(p)) for p in parts)


def build(dotnet='dotnet', root=ROOT):
    """Compile every supported ABI and write fixed archive names and their checksums."""
    release = os.environ.get('THEMERR_VERSION') or runpy.run_path(str(root / 'src/common/version.py'))['VERSION']
    if os.environ.get('THEMERR_VERSION'):
        (root / 'src/common/version.py').write_text(
            f'"""Release identity stamped by the release setup action."""\n\nVERSION = {release!r}\n', encoding='utf-8')
    identity = build_identity(root, release)
    base_version = assembly_version(release)
    directory = root / 'jellyfin-connector'
    directory.mkdir(exist_ok=True)
    artifacts = {}
    for index, (profile, (abi, framework)) in enumerate(PROFILES.items()):
        parts = base_version.split('.')
        parts[-1] = str(int(parts[-1]) * len(PROFILES) + index)
        version = '.'.join(parts)
        if int(parts[-1]) > 65535:
            raise ValueError('Release revision is too large for the connector compatibility matrix.')
        with tempfile.TemporaryDirectory(prefix='themerr-connector-') as temp:
            output = Path(temp) / 'out'
            subprocess.run([
                dotnet, 'build', str(root / 'connectors/jellyfin/Themerr.Connector.csproj'),
                '--configuration', 'Release', '--output', str(output),
                '--configfile', str(root / 'connectors/jellyfin/NuGet.Config'),
                f'-p:ConnectorFramework={framework}', f'-p:JellyfinVersion={abi}',
                f'-p:ConnectorBuild={identity}', f'-p:AssemblyVersion={version}',
                f'-p:BaseIntermediateOutputPath={Path(temp) / "obj"}{os.sep}',
            ], check=True)
            archive = directory / f'connector-{profile}.zip'
            with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
                bundle.write(output / 'Themerr.Connector.dll', 'Themerr.Connector.dll')
            artifacts[profile] = {'targetAbi': abi, 'version': version,
                                  'timestamp': datetime.now(timezone.utc).isoformat(),
                                  'checksum': hashlib.md5(archive.read_bytes(), usedforsecurity=False).hexdigest()}
    descriptor = {'build': identity, 'themerrVersion': release, 'protocol': 1, 'artifacts': artifacts}
    (directory / 'bundle.json').write_text(json.dumps(descriptor, indent=2) + '\n', encoding='utf-8')
    return descriptor


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dotnet', default='dotnet')
    build(parser.parse_args().dotnet)
