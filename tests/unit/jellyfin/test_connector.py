"""Exact artifact selection, repository preservation, and build identity validation."""

# standard imports
import json
from unittest.mock import Mock

# lib imports
import pytest
import requests

# local imports
from common import definitions, version
from jellyfin import connector
from media_servers.base import MediaServerError


def test_manifest_has_only_bundled_versions_and_ignores_request_hosts(configured, connector_bundle):
    connector.repository_url('http://themerr.example:9494/prefix')
    manifest = connector.manifest()[0]
    assert manifest['guid'] == connector.PLUGIN_ID
    assert manifest['imageUrl'] == 'http://themerr.example:9494/prefix' + connector.THUMBNAIL_PATH
    assert {item['targetAbi'] for item in manifest['versions']} == {'10.11.0', '12.1.0'}
    assert len({item['version'] for item in manifest['versions']}) == 1
    assert [item['sourceUrl'] for item in manifest['versions']] == [
        'http://themerr.example:9494/prefix/jellyfin/connector/' + filename
        for filename in connector.ARCHIVES.values()
    ]


@pytest.mark.parametrize('server_version, profile', [
    (
        '10.11.6',
        '10.11',
    ),
    (
        '12.1',
        '12',
    ),
    (
        '12.1.0',
        '12',
    ),
    (
        '12.2',
        '12',
    ),
    (
        '12.2.0',
        '12',
    ),
    (
        '12.3',
        '12',
    ),
])
def test_install_preserves_repositories_and_selects_exact_artifact(
        configured, connector_bundle, server_version, profile):
    connection = Mock(server_version=server_version)
    repositories = [
        {
            'Name': 'Other plugins',
            'Url': 'https://other.example/repo.json',
            'Enabled': False,
        },
        {
            'Name': connector.PLUGIN_NAME,
            'Url': 'http://themerr.example:9494/jellyfin/connector/manifest-12.1.json',
            'Enabled': True,
        },
    ]
    connection.json.side_effect = [
        {'Version': server_version}, MediaServerError('Missing connector.', 404), repositories,
        {'versions': [{'version': connector_bundle['artifacts'][profile]['version'],
                       'repositoryUrl': 'http://themerr.example:9494' + connector.PROFILE_MANIFESTS[profile]}]}, [],
    ]
    result = connector.install(connection, 'http://themerr.example:9494')
    assert result['restart_required'] is True
    assert result['version'] == connector_bundle['artifacts'][profile]['version']
    posted = connection.request.call_args_list[0].kwargs['json']
    assert len(posted) == 2
    assert posted[0] == repositories[0]
    assert posted[1]['Url'] == 'http://themerr.example:9494' + connector.PROFILE_MANIFESTS[profile]
    assert connection.request.call_args_list[1].kwargs['params'] == {
        'assemblyGuid': connector.PLUGIN_ID,
        'version': connector_bundle['artifacts'][profile]['version'],
        'repositoryUrl': 'http://themerr.example:9494' + connector.PROFILE_MANIFESTS[profile],
    }


def test_install_does_not_overwrite_an_active_matching_assembly(configured, connector_bundle):
    connection = Mock(server_version='12.1.0')
    connection.json.side_effect = [
        {'Version': '12.1.0'}, {'protocol': 1, 'build': 'a' * 64, 'targetAbi': '12.1.0'}, [],
    ]
    assert connector.install(connection, 'http://themerr.example')['restart_required'] is False
    connection.request.assert_called_once_with('POST', '/Repositories', json=[
        {'Name': connector.PLUGIN_NAME,
         'Url': 'http://themerr.example' + connector.PROFILE_MANIFESTS['12'], 'Enabled': True},
    ])


@pytest.mark.parametrize('key', connector.ARCHIVES)
def test_profile_repository_has_only_the_requested_abi(configured, connector_bundle, key):
    connector.repository_url('http://themerr.example')
    versions = connector.manifest(key)[0]['versions']
    assert len(versions) == 1
    assert versions[0]['targetAbi'] == connector.PROFILES[key]['JellyfinMinimumVersion']
    assert versions[0]['version'] == connector_bundle['artifacts'][key]['version']


@pytest.mark.parametrize('status', ['Active', 'Disabled', 'Malfunctioned', 'Deleted', 'Restart'])
def test_changed_build_with_same_version_is_unloaded_before_reinstallation(configured, connector_bundle, status):
    release = connector_bundle['artifacts']['12']['version']
    connection = Mock(server_version='12.1.0')
    connection.json.side_effect = [
        {'Version': '12.1.0'}, MediaServerError('Mismatch', 409), [],
        {'versions': [{'version': release,
                       'repositoryUrl': 'http://themerr.example' + connector.PROFILE_MANIFESTS['12']}]},
        [{'Id': connector.PLUGIN_ID.replace('-', ''), 'Version': release, 'Status': status}],
    ]
    result = connector.install(connection, 'http://themerr.example')
    assert result['restart_required']
    assert bool(result.get('reinstall_required')) == (status != 'Restart')
    calls = connection.request.call_args_list
    assert not any(call.args[1].startswith('/Packages/Installed') for call in calls)
    assert len(calls) == (1 if status in ('Deleted', 'Restart') else 2)
    if len(calls) == 2:
        assert calls[1].args == ('DELETE', '/Plugins/' + connector.PLUGIN_ID + '/' + release)


def test_older_connector_versions_are_removed_on_a_downgrade(configured, connector_bundle):
    release = connector_bundle['artifacts']['12']['version']
    connection = Mock(server_version='12.1.0')
    connection.json.side_effect = [
        {'Version': '12.1.0'}, MediaServerError('Mismatch', 409), [],
        {'versions': [{'version': release,
                       'repositoryUrl': 'http://themerr.example' + connector.PROFILE_MANIFESTS['12']}]},
        [{'Id': connector.PLUGIN_ID, 'Version': '2026.1005.9999.0', 'Status': 'Active'},
         {'Id': connector.LEGACY_PLUGIN_ID, 'Version': '2026.1005.9999.0', 'Status': 'Active'}],
    ]
    result = connector.install(connection, 'http://themerr.example')
    assert not result.get('reinstall_required')
    assert connection.request.call_args_list[1].args == (
        'DELETE', '/Plugins/' + connector.PLUGIN_ID + '/2026.1005.9999.0')
    assert connection.request.call_args_list[2].args == ('POST', '/Packages/Installed/' + connector.PLUGIN_NAME)


def test_loaded_connector_marked_restart_is_not_mistaken_for_a_pending_install(configured, connector_bundle):
    release = connector_bundle['artifacts']['12']['version']
    connection = Mock(server_version='12.1.0')
    connection.json.side_effect = [
        {'Version': '12.1.0'},
        MediaServerError('Mismatch', 409),
        [],
        {'versions': [
            {
                'version': release,
                'repositoryUrl': f'http://themerr.example{connector.PROFILE_MANIFESTS["12"]}',
            },
        ]},
        [{
            'Id': connector.PLUGIN_ID,
            'Version': release,
            'Status': 'Restart',
            'ConfigurationFileName': 'Themerr.Connector.xml',
        }],
    ]
    result = connector.install(connection, 'http://themerr.example')
    assert result['reinstall_required'] is True
    assert connection.request.call_args_list[1].args == ('DELETE', f'/Plugins/{connector.PLUGIN_ID}/{release}')
    assert not any(call.args[1].startswith('/Packages/Installed') for call in connection.request.call_args_list)


@pytest.mark.parametrize('status', [
    'Active',
    'Disabled',
    'Malfunctioned',
    'Deleted',
    'Restart',
])
def test_removal_requires_the_conflicting_version_to_disappear(status):
    connection = Mock()
    connection.json.return_value = [{
        'Id': connector.PLUGIN_ID.replace('-', ''),
        'Version': '0.0.0.0',
        'Status': status,
    }]
    with pytest.raises(MediaServerError, match='Stop Jellyfin completely') as error:
        connector.verify_removed(connection, '0.0.0.0')
    assert error.value.status_code == 409
    connection.request.assert_not_called()


def test_removed_version_allows_reinstallation_with_unrelated_plugins_present():
    connection = Mock()
    connection.json.return_value = [
        {
            'Id': connector.LEGACY_PLUGIN_ID,
            'Version': '0.0.0.0',
        },
        {
            'Id': connector.PLUGIN_ID,
            'Version': '1.0.0.0',
        },
    ]
    connector.verify_removed(connection, '0.0.0.0')
    connection.json.assert_called_once_with('GET', '/Plugins')
    connection.request.assert_not_called()


@pytest.mark.parametrize('plugins', [
    None,
    {},
    ['invalid'],
])
def test_invalid_plugin_lists_do_not_confirm_removal(plugins):
    connection = Mock()
    connection.json.return_value = plugins
    with pytest.raises(MediaServerError, match='invalid plugin list'):
        connector.verify_removed(connection, '0.0.0.0')


@pytest.mark.parametrize('status', [
    401,
    403,
    409,
    502,
])
def test_verification_preserves_access_and_connection_errors(configured, connector_bundle, status):
    connection = Mock(server_version='12.1.0')
    failure = MediaServerError('Jellyfin access failed.', status)
    connection.json.side_effect = failure
    with pytest.raises(MediaServerError) as error:
        connector.verify(connection)
    assert error.value is failure


@pytest.mark.parametrize('status', [
    401,
    403,
    502,
])
def test_install_does_not_change_server_on_verification_access_failure(configured, connector_bundle, status):
    connection = Mock(server_version='12.1.0')
    failure = MediaServerError('Jellyfin access failed.', status)
    connection.json.side_effect = [
        {'Version': '12.1.0'},
        failure,
    ]
    with pytest.raises(MediaServerError) as error:
        connector.install(connection, 'http://themerr.example')
    assert error.value is failure
    connection.request.assert_not_called()
    assert connector.repository_url(required=False) is None


def test_verification_reports_missing_connector_as_a_setup_requirement(configured, connector_bundle):
    connection = Mock(server_version='12.1.0')
    connection.json.side_effect = MediaServerError('Unavailable', 404)
    with pytest.raises(MediaServerError, match='matching Themerr connector') as error:
        connector.verify(connection)
    assert error.value.status_code == 409


@pytest.mark.parametrize('field, value', [('protocol', 2), ('build', 'b' * 64), ('targetAbi', '10.11.0')])
def test_mismatched_connector_is_rejected(configured, connector_bundle, field, value):
    connection = Mock(server_version='12.1.0')
    connection.json.return_value = {'protocol': 1, 'build': 'a' * 64, 'targetAbi': '12.1.0', field: value}
    with pytest.raises(MediaServerError, match='matching Themerr connector') as error:
        connector.verify(connection)
    assert error.value.status_code == 409


@pytest.mark.parametrize('release', [
    '10.10.7',
    '10.12.0',
    '11.0',
    '12.0.0',
    '13.0.0',
    '12.2-rc1',
    '12.2.0-rc1',
    '12.2.0+build',
    '12.2.0.0.0',
    '12.02',
    '12.2/traversal',
    '12.2\n',
    None,
])
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
                  'artifacts': {
                      series: {'targetAbi': values['JellyfinMinimumVersion']}
                      for series, values in connector.PROFILES.items()
                  }}
    (directory / 'bundle.json').write_text(json.dumps(descriptor), encoding='utf-8')
    monkeypatch.setattr(definitions.Paths, 'ROOT_DIR', str(frozen))
    assert connector.directory() == directory
    assert connector.bundle() == descriptor


def test_repository_certificate_error_explains_the_http_fallback(configured, connector_bundle, monkeypatch):
    get = Mock(side_effect=requests.exceptions.SSLError('private TLS details'))
    monkeypatch.setattr(connector.requests, 'get', get)
    connection = Mock(server_version='12.1.0')
    connection.json.side_effect = [{'Version': '12.1.0'}, MediaServerError('Mismatch', 409), []]
    with pytest.raises(MediaServerError, match='connector-only HTTP port') as error:
        connector.install(connection, 'https://themerr.example')
    assert error.value.status_code == 400
    assert 'private TLS details' not in str(error.value)
    assert 'headers' not in get.call_args.kwargs
    assert 'verify' not in get.call_args.kwargs
    connection.request.assert_not_called()
    assert connector.repository_url(required=False) is None


def test_repository_failure_reports_jellyfins_download_problem():
    connection = Mock()
    connection.json.side_effect = MediaServerError('Unavailable', 404)
    with pytest.raises(MediaServerError, match='firewall') as error:
        connector._check_repository(connection, 'http://themerr.example', {})
    assert error.value.status_code == 502


def test_legacy_cleanup_preserves_unrelated_plugins_and_repositories():
    connection = Mock()
    legacy = {'Id': connector.LEGACY_PLUGIN_ID, 'Version': '2026.1004.1.0', 'Status': 'Active'}
    other = {'Id': '1' * 32, 'Version': '1.0.0.0', 'Name': 'Themerr', 'Status': 'Active'}
    dedicated = {'Name': 'Themerr', 'Url': connector.LEGACY_REPOSITORY}
    unrelated = {'Name': 'Other', 'Url': 'https://other.example/manifest.json', 'Enabled': False}
    similar = {'Name': 'Other', 'Url': connector.LEGACY_REPOSITORY + '?other=true'}
    connection.json.side_effect = [[legacy, other], [dedicated, unrelated, similar]]
    assert connector.remove_legacy(connection)
    assert connection.request.call_args_list[0].args == (
        'DELETE', '/Plugins/' + connector.LEGACY_PLUGIN_ID + '/2026.1004.1.0')
    assert connection.request.call_args_list[1].kwargs['json'] == [unrelated, similar]


def test_legacy_cleanup_rejects_invalid_versions_without_deleting_anything():
    connection = Mock()
    connection.json.return_value = [{'Id': connector.LEGACY_PLUGIN_ID, 'Version': '../outside'}]
    with pytest.raises(MediaServerError, match='invalid legacy plugin version'):
        connector.remove_legacy(connection)
    connection.request.assert_not_called()
