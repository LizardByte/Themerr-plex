"""Exact artifact selection, repository preservation, and build identity validation."""

import json
from unittest.mock import Mock

import pytest

from common import definitions, version
from jellyfin import connector
from media_servers.base import MediaServerError


def test_manifest_has_only_bundled_versions_and_ignores_request_hosts(configured, connector_bundle):
    connector.repository_url('http://themerr.example:9494/prefix')
    manifest = connector.manifest()[0]
    assert manifest['guid'] == connector.PLUGIN_ID
    assert {item['targetAbi'] for item in manifest['versions']} == {'10.11.0', '12.1.0'}
    assert len({item['version'] for item in manifest['versions']}) == 2
    assert [item['sourceUrl'] for item in manifest['versions']] == [
        'http://themerr.example:9494/prefix/jellyfin/connector/' + filename
        for filename in connector.ARCHIVES.values()
    ]


@pytest.mark.parametrize('server_version, profile', [('10.11.6', '10.11'), ('12.1.0', '12.1')])
def test_install_preserves_repositories_and_selects_exact_artifact(
        configured, connector_bundle, server_version, profile):
    connection = Mock(server_version=server_version)
    repositories = [{'Name': 'Other plugins', 'Url': 'https://other.example/repo.json', 'Enabled': False}]
    connection.json.side_effect = [
        {'Version': server_version}, MediaServerError('Missing connector.', 404), repositories,
    ]
    result = connector.install(connection, 'http://themerr.example:9494')
    assert result['restart_required'] is True
    assert result['version'] == connector_bundle['artifacts'][profile]['version']
    posted = connection.request.call_args_list[0].kwargs['json']
    assert posted[0] == repositories[0]
    assert posted[1]['Url'] == 'http://themerr.example:9494' + connector.MANIFEST_PATH
    assert connection.request.call_args_list[1].kwargs['params'] == {
        'assemblyGuid': connector.PLUGIN_ID,
        'version': connector_bundle['artifacts'][profile]['version'],
        'repositoryUrl': 'http://themerr.example:9494' + connector.MANIFEST_PATH,
    }


def test_install_does_not_overwrite_an_active_matching_assembly(configured, connector_bundle):
    connection = Mock(server_version='12.1.0')
    connection.json.side_effect = [
        {'Version': '12.1.0'}, {'protocol': 1, 'build': 'a' * 64, 'targetAbi': '12.1.0'}, [],
    ]
    assert connector.install(connection, 'http://themerr.example')['restart_required'] is False
    connection.request.assert_called_once_with('POST', '/Repositories', json=[
        {'Name': connector.PLUGIN_NAME + ' (Themerr)',
         'Url': 'http://themerr.example' + connector.MANIFEST_PATH, 'Enabled': True},
    ])


@pytest.mark.parametrize('field, value', [('protocol', 2), ('build', 'b' * 64), ('targetAbi', '10.11.0')])
def test_mismatched_connector_is_rejected(configured, connector_bundle, field, value):
    connection = Mock(server_version='12.1.0')
    connection.json.return_value = {'protocol': 1, 'build': 'a' * 64, 'targetAbi': '12.1.0', field: value}
    with pytest.raises(MediaServerError, match='matching Themerr connector') as error:
        connector.verify(connection)
    assert error.value.status_code == 409


@pytest.mark.parametrize('release', ['10.10.7', '12.0.0', '13.0.0', None])
def test_unsupported_abi_is_not_guessed(release):
    with pytest.raises(MediaServerError):
        connector.profile(release)


def test_bundle_stale_version_is_rejected(configured, connector_bundle, monkeypatch):
    monkeypatch.setattr(version, 'VERSION', 'other-build')
    with pytest.raises(MediaServerError) as error:
        connector.bundle()
    assert error.value.status_code == 503


def test_bundle_is_loaded_from_frozen_resources(configured, monkeypatch, tmp_path):
    frozen = tmp_path / 'frozen'
    directory = frozen / 'jellyfin-connector'
    directory.mkdir(parents=True)
    descriptor = {'protocol': 1, 'themerrVersion': version.VERSION, 'build': 'a' * 64,
                  'artifacts': dict.fromkeys(connector.ARCHIVES, {})}
    (directory / 'bundle.json').write_text(json.dumps(descriptor), encoding='utf-8')
    monkeypatch.setattr(definitions.Paths, 'ROOT_DIR', str(frozen))
    assert connector.directory() == directory
    assert connector.bundle() == descriptor
