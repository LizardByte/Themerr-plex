"""Reused connector artifacts must match their source, release, ABI and file contents."""

# standard imports
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import runpy
import sys
from unittest.mock import MagicMock, Mock
import zipfile

# lib imports
import pytest


@pytest.fixture
def builder(tmp_path, monkeypatch):
    monkeypatch.delenv('THEMERR_VERSION', raising=False)
    script = Path(__file__).resolve().parents[2] / 'scripts/build_connector.py'
    module = runpy.run_path(str(script))
    version = tmp_path / module['VERSION_FILE']
    version.parent.mkdir(parents=True)
    version.write_text('VERSION = "2026.1004.120000"', encoding='utf-8')
    sources = tmp_path / 'connectors/jellyfin'
    sources.mkdir(parents=True)
    (sources / 'Controller.cs').write_bytes(b'source\r\n')
    thumbnail = b'\x89PNG\r\n\x1a\nthumbnail'
    (sources / module['THUMBNAIL']).write_bytes(thumbnail)
    artifacts = {}
    directory = tmp_path / 'jellyfin-connector'
    directory.mkdir()
    (directory / module['THUMBNAIL']).write_bytes(thumbnail)
    for profile, values in module['PROFILES'].items():
        abi = values['JellyfinMinimumVersion']
        archive = directory / values['ConnectorArchive']
        with zipfile.ZipFile(archive, 'w') as content:
            content.writestr('Themerr.Connector.dll', b'assembly')
        artifacts[profile] = {'version': '2026.1004.1200.0', 'targetAbi': abi,
                              'checksum': hashlib.md5(archive.read_bytes(), usedforsecurity=False).hexdigest()}
    data = {'protocol': 1, 'build': module['build_identity'](tmp_path),
            'themerrVersion': '2026.1004.120000', 'artifacts': artifacts}
    (directory / 'bundle.json').write_text(json.dumps(data), encoding='utf-8')
    return module, tmp_path, data


def test_reused_bundle_is_portable_across_line_endings(builder):
    module, root, data = builder
    assert module['check_bundle'](root) == data
    (root / 'connectors/jellyfin/Controller.cs').write_bytes(b'source\n')
    assert module['check_bundle'](root) == data


def test_source_fingerprint_is_identical_for_windows_and_posix_ordering(builder, monkeypatch):
    module, _, _ = builder
    identities = []
    path_orders = []
    for path_type in [
        PureWindowsPath,
        PurePosixPath,
    ]:
        class Source(path_type):
            def read_bytes(self):
                return self.name.encode()

        sources = [
            Source('Themerr.Connector.csproj'),
            Source('ThemeState.cs'),
        ]
        path_orders.append([source.name for source in sorted(sources)])
        root = MagicMock()
        monkeypatch.setattr((root / module['CONNECTOR_SOURCE']).glob, 'return_value', sources)
        identities.append(module['build_identity'](root, version='2026.1005.51610'))

    assert path_orders[0] != path_orders[1]
    assert identities[0] == identities[1]


@pytest.mark.parametrize('release, expected', [
    ('0.0.0', '0.0.0.0'), ('0.0.600', '0.0.600.0'), ('1.2.3', '1.2.3.0'),
    ('2026.105.7', '2026.105.0.7'), ('2026.1005.51610', '2026.1005.516.10'),
    ('2026.1005.120000', '2026.1005.1200.0'), ('2026.1231.235959', '2026.1231.2359.59'),
    ('2026.1005.516.10', '2026.1005.516.10'),
])
def test_dotnet_mapping_matches_release_setup(builder, release, expected):
    module, _, _ = builder
    assert module['assembly_version'](release) == expected


@pytest.mark.parametrize('change', [
    'source', 'thumbnail_source', 'thumbnail_bundle', 'release', 'checksum', 'abi', 'version', 'extra_file',
])
def test_stale_or_modified_bundles_fail_before_packaging(builder, monkeypatch, change):
    module, root, data = builder
    directory = root / 'jellyfin-connector'
    if change == 'source':
        (root / 'connectors/jellyfin/Controller.cs').write_text('changed', encoding='utf-8')
    elif change == 'thumbnail_source':
        # Binary line endings must remain part of the build identity.
        (root / 'connectors/jellyfin' / module['THUMBNAIL']).write_bytes(b'\x89PNG\n\x1a\nthumbnail')
    elif change == 'thumbnail_bundle':
        (directory / module['THUMBNAIL']).write_bytes(b'changed')
    elif change == 'release':
        monkeypatch.setenv('THEMERR_VERSION', '2026.1004.130000')
    elif change == 'checksum':
        (directory / 'connector-12.zip').write_bytes(b'changed')
    elif change == 'abi':
        data['artifacts']['12']['targetAbi'] = '13.0.0'
    elif change == 'version':
        data['artifacts']['12']['version'] = '2026.1004.1200.1'
    else:
        archive = directory / 'connector-12.zip'
        with zipfile.ZipFile(archive, 'a') as content:
            content.writestr('unexpected.txt', 'unexpected')
        data['artifacts']['12']['checksum'] = hashlib.md5(
            archive.read_bytes(), usedforsecurity=False).hexdigest()
    (directory / 'bundle.json').write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError):
        module['check_bundle'](root)


def test_build_uses_fixed_dotnet_command_and_produces_a_valid_bundle(builder, monkeypatch):
    module, root, _ = builder

    def compile_connector(command, **kwargs):
        output = Path(command[command.index('--output') + 1])
        output.mkdir()
        (output / module['ASSEMBLY_FILE']).write_bytes(b'compiled assembly')

    run = Mock(side_effect=compile_connector)
    monkeypatch.setattr(module['subprocess'], 'run', run)
    descriptor = module['build'](root=root)

    assert module['check_bundle'](root) == descriptor
    assert run.call_count == len(module['PROFILES'])
    assert all(call.args[0][0] == 'dotnet' and call.kwargs == {'check': True} for call in run.call_args_list)


@pytest.mark.parametrize('release', [
    '1.2.3;-p:Injected=true',
    '1.2.3\n-p:Injected=true',
    '1.2.3 -p:Injected=true',
])
def test_build_rejects_release_arguments_before_starting_a_process(builder, monkeypatch, release):
    module, root, _ = builder
    run = Mock()
    monkeypatch.setattr(module['subprocess'], 'run', run)
    monkeypatch.setenv('THEMERR_VERSION', release)

    with pytest.raises(ValueError, match='valid four-part .NET version'):
        module['build'](root=root)
    run.assert_not_called()


def test_cli_rejects_executable_overrides(builder, monkeypatch):
    module, _, _ = builder
    run = Mock()
    script = Path(__file__).resolve().parents[2] / 'scripts/build_connector.py'
    monkeypatch.setattr(module['subprocess'], 'run', run)
    monkeypatch.setattr(sys, 'argv', [
        str(script),
        '--dotnet',
        'unapproved-executable',
    ])

    with pytest.raises(SystemExit) as error:
        runpy.run_path(str(script), run_name='__main__')
    assert error.value.code == 2
    run.assert_not_called()
