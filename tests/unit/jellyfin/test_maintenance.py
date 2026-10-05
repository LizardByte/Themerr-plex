"""Connector lifecycle decisions with mocked Jellyfin APIs and a real temporary state store."""

from unittest.mock import Mock
from threading import Event

import pytest

from jellyfin import connector, maintenance, servers
from media_servers.base import MediaServerError

SERVER = 'jellyfin:' + '3' * 32


@pytest.fixture
def connection(configured, connector_bundle, monkeypatch):
    value = Mock(server_version='12.1.0')
    monkeypatch.setattr(servers, 'client', lambda _: value)
    monkeypatch.setattr(maintenance.time, 'time', lambda: 1000)
    monkeypatch.setattr(maintenance, '_stop', Event())
    monkeypatch.setattr(connector, 'install', Mock(return_value={
        'restart_required': True, 'message': 'Installed', 'version': '2026.1004.1.0'}))
    monkeypatch.setattr(connector, 'remove_legacy', Mock(return_value=False))
    return value


def test_install_notifies_before_restart_and_persists_progress(connection, monkeypatch):
    result = maintenance.install(SERVER, 'http://themerr.example')
    assert 'playback finishes' in result['message']
    assert maintenance.state(SERVER)['restart_after'] == 1030
    maintenance._restart(SERVER, connection, maintenance.state(SERVER))
    connection.request.assert_not_called()
    monkeypatch.setattr(maintenance.time, 'time', lambda: 1031)
    connection.json.side_effect = [[{'NowPlayingItem': {'Id': 'playing'}, 'PlayState': {'IsPaused': True}}]]
    maintenance._restart(SERVER, connection, maintenance.state(SERVER))
    assert 'Waiting' in maintenance.state(SERVER)['message']
    connection.request.assert_not_called()
    connection.json.side_effect = [[], {'CanSelfRestart': True}]
    maintenance._restart(SERVER, connection, maintenance.state(SERVER))
    connection.request.assert_called_once_with('POST', '/System/Restart')
    assert maintenance.state(SERVER)['phase'] == 'restarting'


@pytest.mark.parametrize('option', ['AUTO_RESTART', 'WAIT_FOR_IDLE'])
def test_restart_preferences_are_independent(connection, configured, monkeypatch, option):
    configured['Jellyfin'][option] = False
    result = maintenance.install(SERVER, 'http://themerr.example')
    monkeypatch.setattr(maintenance.time, 'time', lambda: 1031)
    connection.json.return_value = {'CanSelfRestart': True}
    maintenance._restart(SERVER, connection, maintenance.state(SERVER))
    if option == 'AUTO_RESTART':
        assert 'disabled' in result['message']
        connection.request.assert_not_called()
    else:
        assert 'shortly' in result['message']
        connection.json.assert_called_once_with('GET', '/System/Info')
        connection.request.assert_called_once_with('POST', '/System/Restart')


@pytest.mark.parametrize('sessions', [None, ['invalid']])
def test_invalid_session_data_never_triggers_a_restart(connection, sessions):
    connection.json.return_value = sessions
    with pytest.raises(MediaServerError, match='restart deferred'):
        maintenance._restart(SERVER, connection, {})
    connection.request.assert_not_called()


def test_service_or_container_without_self_restart_gets_manual_instructions(connection):
    connection.json.side_effect = [[], {'CanSelfRestart': False}]
    maintenance._restart(SERVER, connection, {})
    assert maintenance.state(SERVER)['phase'] == 'manual'
    connection.request.assert_not_called()


def test_startup_installs_a_mismatch_only_when_configured(connection, configured, monkeypatch):
    monkeypatch.setattr(connector, 'verify', Mock(side_effect=MediaServerError('Mismatch', 409)))
    maintenance.maintain(SERVER)
    connector.install.assert_not_called()
    connector.repository_url('http://themerr.example')
    configured['Jellyfin']['AUTO_UPDATE_CONNECTOR'] = False
    maintenance.maintain(SERVER)
    connector.install.assert_not_called()
    configured['Jellyfin']['AUTO_UPDATE_CONNECTOR'] = True
    maintenance.maintain(SERVER)
    connector.install.assert_called_once_with(connection, 'http://themerr.example')


def test_loaded_connector_refreshes_libraries_after_restart(connection, monkeypatch):
    from jellyfin.backend import JellyfinMediaServer
    maintenance._save(SERVER, phase='restarting', restart_started=999, restart_required=True)
    monkeypatch.setattr(connector, 'verify', Mock(return_value={}))
    refresh = Mock(return_value=True)
    record = Mock()
    monkeypatch.setattr(JellyfinMediaServer, 'cache_dashboard', refresh)
    monkeypatch.setattr(servers, 'record_refresh', record)
    maintenance.maintain(SERVER)
    refresh.assert_called_once_with()
    record.assert_called_once_with(SERVER)
    assert maintenance.state(SERVER)['restart_required'] is False


def test_legacy_cleanup_requires_restart_even_with_matching_connector(connection, configured, monkeypatch):
    configured['Jellyfin']['REMOVE_LEGACY_PLUGIN'] = True
    connector.install.return_value['restart_required'] = False
    monkeypatch.setattr(connector, 'remove_legacy', Mock(return_value=True))
    monkeypatch.setattr(connector, 'verify', Mock(return_value={}))
    assert maintenance.install(SERVER, 'http://themerr.example')['restart_required']
    monkeypatch.setattr(maintenance.time, 'time', lambda: 1031)
    connection.json.side_effect = [{'HasPendingRestart': True}, [], {'CanSelfRestart': True}]
    maintenance.maintain(SERVER)
    connection.request.assert_called_once_with('POST', '/System/Restart')


def test_default_legacy_cleanup_without_old_plugin_does_not_add_a_restart(connection, configured):
    assert configured['Jellyfin']['REMOVE_LEGACY_PLUGIN'] is True
    connector.install.return_value['restart_required'] = False
    result = maintenance.install(SERVER, 'http://themerr.example')
    connector.remove_legacy.assert_called_once_with(connection)
    assert result['restart_required'] is False
    assert maintenance.state(SERVER)['phase'] == 'active'
    assert maintenance.state(SERVER)['legacy_checked'] == connector.bundle()['build']


@pytest.mark.parametrize('phase', ['pending', 'manual', 'restarting'])
def test_legacy_cleanup_waits_for_and_recognizes_a_manual_restart(connection, monkeypatch, phase):
    from jellyfin.backend import JellyfinMediaServer
    maintenance._save(SERVER, phase=phase, restart_started=999, restart_after=2000, restart_required=True,
                      force_restart=True, build=connector.bundle()['build'])
    monkeypatch.setattr(connector, 'verify', Mock(return_value={}))
    refresh = Mock()
    record = Mock()
    monkeypatch.setattr(JellyfinMediaServer, 'cache_dashboard', refresh)
    monkeypatch.setattr(servers, 'record_refresh', record)
    connection.json.return_value = {'HasPendingRestart': True}
    maintenance.maintain(SERVER)
    refresh.assert_not_called()
    assert maintenance.state(SERVER)['restart_required']
    connection.request.assert_not_called()
    connection.json.return_value = {'HasPendingRestart': False}
    maintenance.maintain(SERVER)
    refresh.assert_called_once_with()
    record.assert_called_once_with(SERVER)
    assert maintenance.state(SERVER)['restart_required'] is False
    assert maintenance.state(SERVER)['force_restart'] is False
    connection.request.assert_not_called()


def test_failed_library_refresh_retains_restart_progress_for_retry(connection, monkeypatch):
    from jellyfin.backend import JellyfinMediaServer
    maintenance._save(SERVER, phase='restarting', restart_started=999, restart_required=True)
    monkeypatch.setattr(connector, 'verify', Mock(return_value={}))
    monkeypatch.setattr(JellyfinMediaServer, 'cache_dashboard', Mock(side_effect=MediaServerError('Unavailable', 502)))
    with pytest.raises(MediaServerError):
        maintenance.maintain(SERVER)
    assert maintenance.state(SERVER)['restart_required']
    assert maintenance.state(SERVER)['phase'] == 'restarting'


def test_unavailable_server_after_restart_times_out_without_restarting_again(connection, monkeypatch):
    maintenance._save(SERVER, phase='restarting', restart_started=1, restart_required=True)
    monkeypatch.setattr(servers, 'list_servers', lambda **_: [{'id': SERVER}])
    monkeypatch.setattr(servers, 'client', Mock(side_effect=MediaServerError('Unavailable', 502)))
    maintenance.reconcile()
    assert maintenance.state(SERVER)['phase'] == 'manual'
    connection.request.assert_not_called()


def test_shutdown_cancels_a_restart_after_an_in_flight_idle_check(connection):
    def check(method, route):
        if route == '/System/Info':
            maintenance.stop()
            return {'CanSelfRestart': True}
        return []
    connection.json.side_effect = check
    maintenance._restart(SERVER, connection, {})
    connection.request.assert_not_called()


def test_force_restart_bypasses_automatic_preferences_and_active_playback(connection, configured):
    configured['Jellyfin']['AUTO_RESTART'] = False
    configured['Jellyfin']['WAIT_FOR_IDLE'] = True
    connection.json.return_value = {'CanSelfRestart': True}
    result = maintenance.force_restart(SERVER)
    assert result['phase'] == 'restarting'
    assert result['manual_restart'] is True
    connection.json.assert_called_once_with('GET', '/System/Info')
    connection.request.assert_called_once_with('POST', '/System/Restart')


@pytest.mark.parametrize('info', [None, {}, {'CanSelfRestart': False}])
def test_force_restart_requires_explicit_server_capability(connection, info):
    connection.json.return_value = info
    with pytest.raises(MediaServerError, match='cannot restart itself'):
        maintenance.force_restart(SERVER)
    connection.request.assert_not_called()
    assert maintenance.state(SERVER) == {}


def test_force_restart_without_connector_recovers_without_installing_it(connection, configured, monkeypatch):
    from jellyfin.backend import JellyfinMediaServer
    configured['Jellyfin']['AUTO_UPDATE_CONNECTOR'] = False
    connection.json.return_value = {'CanSelfRestart': True}
    maintenance.force_restart(SERVER)
    verify = Mock()
    refresh = Mock(return_value=True)
    monkeypatch.setattr(connector, 'verify', verify)
    monkeypatch.setattr(JellyfinMediaServer, 'cache_dashboard', refresh)
    monkeypatch.setattr(servers, 'record_refresh', Mock())
    maintenance.maintain(SERVER)
    verify.assert_not_called()
    refresh.assert_called_once_with()
    assert maintenance.state(SERVER)['phase'] == 'active'
    assert maintenance.state(SERVER)['manual_restart'] is False


@pytest.mark.parametrize('phase', ['pending', 'manual', 'restarting'])
def test_same_version_replacement_waits_for_unload_then_installs(connection, monkeypatch, phase):
    connector.install.return_value['reinstall_required'] = True
    maintenance.install(SERVER, 'http://themerr.example')
    maintenance._save(SERVER, phase=phase, restart_started=999)
    verify = Mock()
    monkeypatch.setattr(connector, 'verify', verify)
    connection.json.return_value = {'HasPendingRestart': True}
    maintenance.maintain(SERVER)
    assert connector.install.call_count == 1
    assert maintenance.state(SERVER)['reinstall_required']
    connection.json.return_value = {'HasPendingRestart': False}
    connector.install.return_value.pop('reinstall_required')
    maintenance.maintain(SERVER)
    assert connector.install.call_count == 2
    assert maintenance.state(SERVER)['reinstall_required'] is False
    assert maintenance.state(SERVER)['restart_required']
    assert maintenance.state(SERVER)['phase'] == 'pending'
    verify.assert_not_called()
