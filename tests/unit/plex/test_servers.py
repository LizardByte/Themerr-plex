"""Multi-server discovery, credentials, isolation, and processing boundaries."""

# standard imports
from types import SimpleNamespace
from unittest.mock import Mock

# lib imports
from cryptography.fernet import Fernet
import pytest
from requests.exceptions import ConnectTimeout
from sqlalchemy.orm import Session

# local imports
from plex import auth, plexapi, servers, token_store
from plex import dashboard, media as general, tmdb
from media_servers import processing
from themerr import cache, storage


@pytest.fixture(autouse=True)
def connection_cache():
    servers.clear_connections()
    yield
    servers.clear_connections()


def save_server(identifier, name=None, **kwargs):
    with Session(storage.engine()) as database:
        database.add(servers.ServerRecord(id=identifier, name=name or identifier,
                                          url='http://' + identifier + ':32400', **kwargs))
        database.commit()


def snapshot(title='Example'):
    return {'1': {'key': 1, 'title': 'Movies', 'agent': 'tv.plex.agents.movie', 'type': 'movie',
                  'media_count': 1, 'media_percent_complete': 0, 'collection_count': 0,
                  'collection_percent_complete': 0, 'collections_enabled': False, 'total_count': 1,
                  'items': [{'rating_key': '42', 'title': title, 'type': 'movie', 'theme': False,
                             'theme_status': 'pending'}]}}


def test_storage_rating_keys_sections_errors_and_upload_revisions_are_isolated(configured):
    for identifier in ('a', 'b'):
        save_server(identifier)
        with storage.server_scope(identifier):
            storage.replace_dashboard(snapshot(identifier))
            storage.save_tracking(42, 'movie', {'youtube_theme_url': identifier, 'audio_codec': 'opus'})
            storage.set_error(42, 'error ' + identifier)
    revision = storage.dashboard_revision()
    with storage.server_scope('b'):
        storage.mark_dashboard_theme_uploaded(42, 'themerr')
    with storage.server_scope('a'):
        storage.replace_dashboard(snapshot('a'), since_revision=revision)
        assert storage.get_tracking(42)['youtube_theme_url'] == 'a'
        assert storage.get_errors() == {'42': 'error a'}
        assert storage.get_dashboard()['1']['media_percent_complete'] == 0
    with storage.server_scope('b'):
        storage.replace_dashboard(snapshot('b'), since_revision=revision)
        assert storage.get_tracking(42)['youtube_theme_url'] == 'b'
        assert storage.get_dashboard()['1']['items'][0]['theme_provider'] == 'themerr'
        assert storage.get_dashboard()['1']['media_percent_complete'] == 100
        assert storage.get_errors() == {'42': 'error b'}
    assert storage.current_server_id() == 'default'
    assert storage.get_dashboard() is None
    assert storage.get_tracking(42) == {}


def test_scope_is_restored_when_operation_fails():
    def failing_operation():
        with storage.server_scope('a'):
            with storage.server_scope('b'):
                assert storage.current_server_id() == 'b'
                raise RuntimeError('Operation failed')
    with pytest.raises(RuntimeError, match='Operation failed'):
        failing_operation()
    assert storage.current_server_id() == 'default'


def test_account_discovery_omits_resource_tokens(configured, monkeypatch):
    auth.set_token('account-secret')
    resource = SimpleNamespace(clientIdentifier='one', name='Living room', owned=False,
                               provides='server', accessToken='shared-secret', connections=[
                                   SimpleNamespace(uri='https://plex.example:32400', local=True, relay=False)])
    account = Mock()
    account.resources.return_value = [resource, SimpleNamespace(provides='client')]
    constructor = Mock(return_value=account)
    monkeypatch.setattr(servers, 'MyPlexAccount', constructor)
    assert servers.discover_account() == [{'id': 'one', 'name': 'Living room', 'owned': False,
                                          'connections': [{'url': 'https://plex.example:32400',
                                                           'local': True, 'relay': False}]}]
    constructor.assert_called_once_with(token='account-secret', timeout=10)
    assert 'shared-secret' not in str(servers.discover_account())
    auth.disconnect()
    with pytest.raises(ValueError, match='Connect your Plex account'):
        servers.account_resources()


def test_gdm_discovery_filters_clients_and_bad_ports(configured, monkeypatch):
    discovery = Mock(entries=[
        {'from': ('192.168.1.2', 32414), 'data': {
            'Content-Type': 'plex/media-server', 'Resource-Identifier': 'one', 'Name': 'Local', 'Port': '32400',
        }},
        {'from': ('192.168.1.3', 32414), 'data': {'Content-Type': 'plex/media-player'}},
        {'from': ('192.168.1.4', 32414), 'data': {'Content-Type': 'plex/media-server', 'Port': '65536'}},
        {'from': ('192.168.1.5', 32414), 'data': {'Content-Type': 'plex/media-server', 'Port': 'invalid'}},
    ])
    monkeypatch.setattr(servers, 'GDM', lambda: discovery)
    result = servers.discover_local()
    discovery.scan.assert_called_once_with()
    assert result == [{'id': 'one', 'name': 'Local', 'connections': [
        {'url': 'http://192.168.1.2:32400', 'local': True, 'relay': False}]}]


@pytest.mark.parametrize('url', ['ftp://plex.example', 'https://user:password@plex.example',
                                 'https://plex.example/path', 'http://plex.example?token=abc',
                                 'https://plex.example#fragment', 'http://plex.example:99999', '', None])
def test_invalid_manual_addresses_are_rejected(url):
    with pytest.raises(ValueError):
        servers.validate_url(url)


def test_shared_server_uses_resource_token_and_checks_machine_id(configured, monkeypatch):
    auth.set_token('account-secret')
    resource = SimpleNamespace(clientIdentifier='shared', accessToken='shared-secret')
    monkeypatch.setattr(servers, 'account_resources', lambda: [resource])
    server = SimpleNamespace(machineIdentifier='shared', friendlyName='Family Plex')
    connect = Mock(return_value=server)
    monkeypatch.setattr(plexapi, 'connect_plex_server', connect)
    record = servers.add_server('https://plex.example/', 'shared')
    connect.assert_called_once_with('https://plex.example', 'shared-secret')
    assert record['id'] == 'shared'
    assert record['name'] == 'Family Plex'
    assert 'secret' not in str(record)
    assert token_store.get_token(servers.credential_id('shared')) == 'shared-secret'
    assert servers.connect('shared') is server
    servers.clear_connections()
    assert servers.connect('shared') is server
    assert connect.call_count == 2
    connect.return_value = SimpleNamespace(machineIdentifier='other', friendlyName='Wrong')
    with pytest.raises(ValueError, match='different Plex server'):
        servers.add_server('http://other.example', 'shared')
    assert servers.get_server('shared')['url'] == 'https://plex.example'
    with pytest.raises(ValueError, match='not available'):
        servers.add_server('http://plex.example', 'missing')
    servers.clear_connections()
    with pytest.raises(ValueError, match='different Plex server'):
        servers.connect('shared')


def test_manual_connection_works_when_account_discovery_is_unavailable(configured, monkeypatch):
    auth.set_token('account-secret')
    monkeypatch.setattr(servers, 'account_resources', Mock(side_effect=OSError('offline')))
    server = SimpleNamespace(machineIdentifier='manual', friendlyName='Manual Plex')
    connect = Mock(return_value=server)
    monkeypatch.setattr(plexapi, 'connect_plex_server', connect)
    assert servers.add_server('http://192.168.1.10:32400')['id'] == 'manual'
    connect.assert_called_once_with('http://192.168.1.10:32400', 'account-secret')
    auth.disconnect()
    with pytest.raises(ValueError, match='Connect your Plex account'):
        servers.add_server('http://plex.example')


def test_unreachable_server_does_not_save_credentials_or_register_it(configured, monkeypatch):
    auth.set_token('account-secret')
    monkeypatch.setattr(servers, 'account_resources', lambda: [])
    monkeypatch.setattr(plexapi, 'connect_plex_server', Mock(side_effect=ConnectTimeout('unreachable')))
    save = Mock()
    monkeypatch.setattr(token_store, 'save_token', save)
    with pytest.raises(ConnectTimeout):
        servers.add_server('https://unreachable.example:32400')
    save.assert_not_called()
    assert servers.list_servers() == []
    assert servers._connections == {}


def test_server_preferences_pause_and_remove_only_selected_server(configured, monkeypatch):
    for identifier in ('a', 'b'):
        save_server(identifier)
        token_store.save_token(servers.credential_id(identifier), 'token-' + identifier)
        with storage.server_scope(identifier):
            storage.replace_dashboard(snapshot(identifier))
            storage.save_tracking(42, 'movie', {'youtube_theme_url': identifier})
            storage.set_error(42, identifier)
    servers.update_server('a', {'enabled': False, 'data_directory': '', 'ignored_libraries': '2, 3'})
    assert servers.connect('a') is None
    assert [row['id'] for row in servers.list_servers(enabled_only=True)] == ['b']
    assert servers.connect('missing') is None
    for values in ({'enabled': 'false'}, {'data_directory': None}, {'ignored_libraries': '\x00'}):
        with pytest.raises(ValueError):
            servers.update_server('a', values)
    with pytest.raises(ValueError):
        servers.update_server('missing', {})
    stop = Mock()
    monkeypatch.setattr(plexapi, 'stop_plex_listener', stop)
    servers.remove_server('a')
    stop.assert_called_once_with('a')
    assert token_store.get_token(servers.credential_id('a')) == ''
    with storage.server_scope('a'):
        assert storage.get_dashboard() is None
        assert not storage.get_tracking(42)
        assert not storage.get_errors()
    with storage.server_scope('b'):
        assert storage.get_dashboard()['1']['items'][0]['title'] == 'b'
        assert storage.get_tracking(42)['youtube_theme_url'] == 'b'
    servers.record_refresh('b', 'Offline')
    assert servers.get_server('b')['last_error'] == 'Offline'
    servers.record_refresh('b')
    assert servers.get_server('b')['last_error'] is None
    assert servers.get_server('b')['last_refresh']


def test_external_key_encrypts_independent_account_and_server_tokens(configured, tmp_path, monkeypatch):
    key = tmp_path / 'external.key'
    key.write_bytes(Fernet.generate_key())
    monkeypatch.setenv(token_store.KEY_FILE_ENV, str(key))
    auth.set_token('account-secret')
    for identifier in ('a', 'b'):
        token_store.save_token(servers.credential_id(identifier), 'token-' + identifier)
    assert auth.get_token() == 'account-secret'
    assert token_store.get_token(servers.credential_id('a')) == 'token-a'
    token_store.delete_token(servers.credential_id('a'))
    assert auth.get_token() == 'account-secret'
    assert token_store.get_token(servers.credential_id('b')) == 'token-b'
    assert 'account-secret' not in storage.get_encrypted_token()
    assert b'token-b' not in tmp_path.joinpath('themerr-plex.db').read_bytes()


def test_cache_and_scan_keep_other_servers_running_when_one_is_offline(configured, monkeypatch):
    for identifier in ('a', 'b', 'paused'):
        save_server(identifier, enabled=identifier != 'paused')
    seen = []

    def refresh():
        identifier = storage.current_server_id()
        seen.append(identifier)
        if identifier == 'a':
            raise OSError('offline')
        storage.replace_dashboard(snapshot(identifier))
        return True

    monkeypatch.setattr(dashboard, '_cache_server', refresh)
    cache.cache_data()
    assert seen == ['a', 'b']
    assert servers.get_server('a')['last_error']
    assert servers.get_server('b')['last_refresh']
    seen.clear()
    monkeypatch.setattr(plexapi, 'scan_items', lambda enqueue: refresh())
    processing.scheduled_update()
    assert seen == ['a', 'b']
    assert storage.current_server_id() == 'default'


def test_registry_empty_never_falls_back_to_the_retired_single_connection(configured, monkeypatch):
    scan, refresh = Mock(), Mock()
    monkeypatch.setattr(plexapi, 'scan_items', scan)
    monkeypatch.setattr(dashboard, '_cache_server', refresh)
    processing.scheduled_update()
    cache.cache_data()
    scan.assert_not_called()
    refresh.assert_not_called()


def test_listener_callbacks_and_queue_carry_server_identity(configured, monkeypatch):
    from queue import Queue
    queue = Queue()
    monkeypatch.setattr(processing, 'q', queue)
    monkeypatch.setattr(plexapi, '_alert_listeners', {})
    for identifier in ('a', 'b'):
        save_server(identifier)
    monkeypatch.setattr(plexapi, 'setup_plexapi', lambda: storage.current_server_id())
    listeners = []

    def listener(**kwargs):
        result = Mock(_ws=object())
        listeners.append((kwargs, result))
        return result

    monkeypatch.setattr(plexapi, 'AlertListener', listener)
    plexapi.plex_listener()
    event = {'type': 'timeline', 'TimelineEntry': [
        {'state': 5, 'identifier': 'com.plexapp.plugins.library', 'type': 1, 'itemID': '42'}]}
    for kwargs, _ in listeners:
        kwargs['callback'](event)
        kwargs['callback'](event)
    assert list(queue.queue) == [('a', '42'), ('b', '42')]
    servers.update_server('a', {'enabled': False})
    listeners[0][0]['callback'](event)
    assert queue.qsize() == 2
    plexapi.stop_plex_listener('a')
    listeners[0][1].stop.assert_called_once()
    listeners[1][1].stop.assert_not_called()
    plexapi.stop_plex_listener()
    listeners[1][1].stop.assert_called_once()


def test_proxy_and_metadata_paths_follow_current_server(configured, monkeypatch, item):
    for identifier in ('a', 'b'):
        save_server(identifier, data_directory='C:/Plex-' + identifier)
        token_store.save_token(servers.credential_id(identifier), 'token-' + identifier)
    response = Mock()
    response.json.return_value = {'movie_results': [{'id': 99}]}
    get = Mock(return_value=response)
    monkeypatch.setattr(tmdb.requests, 'get', get)
    tmdb._proxy_cache.clear()
    for identifier in ('a', 'b'):
        with storage.server_scope(identifier):
            assert tmdb.query('find/tt42', {})['movie_results'][0]['id'] == 99
            assert get.call_args.args[0] == 'http://' + identifier + ':32400/services/tmdb'
            assert get.call_args.kwargs['headers']['X-Plex-Token'] == 'token-' + identifier
            assert general.get_media_upload_path(item, 'themes').startswith('C:/Plex-' + identifier)
    servers.update_server('a', {'data_directory': '', 'enabled': False})
    with storage.server_scope('a'):
        assert general.get_media_upload_path(item, 'themes') == ''
        assert tmdb.query('find/tt42', {}) == {}


def test_workers_keep_server_scope_deduplicate_active_work_and_release_failed_items(monkeypatch):
    monkeypatch.setattr(processing, '_active_items', set())
    queue = processing._WorkQueue()
    monkeypatch.setattr(processing, 'q', queue)
    monkeypatch.setattr(servers, 'get_server', lambda identifier: {'enabled': identifier != 'paused'})
    for identifier in ('a', 'b', 'paused'):
        with storage.server_scope(identifier):
            assert processing.enqueue(42)
            assert not processing.enqueue(42)
    seen = []

    def update(rating_key):
        identifier = storage.current_server_id()
        seen.append((identifier, rating_key))
        assert not processing.enqueue(rating_key)
        if identifier == 'a':
            raise RuntimeError('One server failed')

    get = queue.get

    def next_work():
        if queue.empty():
            raise KeyboardInterrupt
        return get()

    monkeypatch.setattr(queue, 'get', next_work)
    monkeypatch.setattr(plexapi, 'update_plex_item', update)
    with pytest.raises(KeyboardInterrupt):
        processing.process_queue()
    assert seen == [('a', 42), ('b', 42)]
    assert queue.unfinished_tasks == 0
    assert not processing._active_items
    assert storage.current_server_id() == 'default'
    with storage.server_scope('a'):
        assert processing.enqueue(42)


def test_manual_address_uses_shared_server_resource_token(configured, monkeypatch):
    auth.set_token('account-token')
    resource = SimpleNamespace(clientIdentifier='shared', accessToken='shared-token', connections=[
        SimpleNamespace(uri='https://shared.example:32400/')])
    monkeypatch.setattr(servers, 'account_resources', lambda: [resource])
    connect = Mock(return_value=SimpleNamespace(machineIdentifier='shared', friendlyName='Shared server'))
    monkeypatch.setattr(plexapi, 'connect_plex_server', connect)
    assert servers.add_server('https://shared.example:32400')['id'] == 'shared'
    connect.assert_called_once_with('https://shared.example:32400', 'shared-token')
