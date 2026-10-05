"""Reused connector artifacts must match their source, release, ABI and file contents."""

import hashlib
import json
from pathlib import Path
import runpy
import zipfile

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
    artifacts = {}
    directory = tmp_path / 'jellyfin-connector'
    directory.mkdir()
    for profile, (abi, _) in module['PROFILES'].items():
        archive = directory / ('connector-' + profile + '.zip')
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


@pytest.mark.parametrize('change', ['source', 'release', 'checksum', 'abi', 'extra_file'])
def test_stale_or_modified_bundles_fail_before_packaging(builder, monkeypatch, change):
    module, root, data = builder
    directory = root / 'jellyfin-connector'
    if change == 'source':
        (root / 'connectors/jellyfin/Controller.cs').write_text('changed', encoding='utf-8')
    elif change == 'release':
        monkeypatch.setenv('THEMERR_VERSION', '2026.1004.130000')
    elif change == 'checksum':
        (directory / 'connector-12.1.zip').write_bytes(b'changed')
    elif change == 'abi':
        data['artifacts']['12.1']['targetAbi'] = '13.0.0'
    else:
        archive = directory / 'connector-12.1.zip'
        with zipfile.ZipFile(archive, 'a') as content:
            content.writestr('unexpected.txt', 'unexpected')
        data['artifacts']['12.1']['checksum'] = hashlib.md5(
            archive.read_bytes(), usedforsecurity=False).hexdigest()
    (directory / 'bundle.json').write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError):
        module['check_bundle'](root)
