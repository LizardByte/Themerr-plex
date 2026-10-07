"""The smoke-test catalog stays private and only its own Docker resources are removed."""

# standard imports
from contextlib import nullcontext
import json
from pathlib import Path
import runpy
import subprocess
from unittest.mock import Mock

# lib imports
import pytest

# local imports
from jellyfin import connector


@pytest.fixture
def smoke_script(monkeypatch):
    scripts = Path(__file__).resolve().parents[2] / 'scripts'
    monkeypatch.syspath_prepend(str(scripts))
    return runpy.run_path(str(scripts / 'smoke_connector.py'))


@pytest.mark.parametrize('fail_validation', [
    False,
    True,
])
def test_repository_exports_real_routes_without_a_host_listener(
        configured, connector_bundle, smoke_script, monkeypatch, fail_validation):
    run = Mock()
    monkeypatch.setitem(smoke_script['repository_server'].__wrapped__.__globals__, 'docker', run)
    original_repository_url = connector.repository_url
    catalog = None

    with pytest.raises(RuntimeError, match='validation failed') if fail_validation else nullcontext():
        with smoke_script['repository_server']() as (network, url):
            arguments = run.call_args.args
            mount = arguments[arguments.index('--mount') + 1]
            catalog = Path(mount.split('source=', 1)[1].split(',target=', 1)[0])
            assert '--publish' not in arguments
            assert arguments[arguments.index('--network') + 1] == network
            assert mount.endswith(',readonly')
            assert run.call_args_list[0].args == (
                'network',
                'create',
                '--driver',
                'bridge',
                network,
            )
            assert url == f'http://{network}-repository'

            for route in connector.PUBLIC_PATHS:
                assert (catalog / route.lstrip('/')).is_file()
            for route, series in connector.MANIFEST_PROFILES.items():
                manifest = json.loads((catalog / route.lstrip('/')).read_bytes())[0]
                assert len(manifest['versions']) == 1
                assert manifest['versions'][0]['targetAbi'] == connector_bundle['artifacts'][series]['targetAbi']
                assert manifest['versions'][0]['sourceUrl'] == f'{url}/jellyfin/connector/{connector.ARCHIVES[series]}'
            for route, filename in connector.ARCHIVE_PATHS.items():
                assert (catalog / route.lstrip('/')).read_bytes() == (connector.directory() / filename).read_bytes()
            if fail_validation:
                raise RuntimeError('validation failed')

    assert run.call_args_list[-2].args == (
        'rm',
        '--force',
        '--volumes',
        f'{network}-repository',
    )
    assert run.call_args_list[-1].args == (
        'network',
        'rm',
        network,
    )
    assert not catalog.exists()
    assert connector.repository_url is original_repository_url


def test_repository_start_failure_removes_its_network(
        configured, connector_bundle, smoke_script, monkeypatch):
    def fail_start(*arguments):
        if arguments[0] == 'run':
            raise RuntimeError('repository start failed')

    run = Mock(side_effect=fail_start)
    monkeypatch.setitem(smoke_script['repository_server'].__wrapped__.__globals__, 'docker', run)
    server = smoke_script['repository_server']()
    with pytest.raises(RuntimeError, match='repository start failed'):
        server.__enter__()

    network = run.call_args_list[0].args[-1]
    assert run.call_args_list[-1].args == (
        'network',
        'rm',
        network,
    )
    assert not any(call.args[0] == 'rm' for call in run.call_args_list)


def test_server_url_requires_a_running_loopback_binding(smoke_script, monkeypatch):
    container = {
        'State': {
            'Running': True,
            'Status': 'running',
            'ExitCode': 0,
        },
        'NetworkSettings': {
            'Ports': {
                '8096/tcp': [{
                    'HostIp': '127.0.0.1',
                    'HostPort': '49152',
                }],
            },
        },
    }
    run = Mock(return_value=json.dumps([container]))
    monkeypatch.setitem(smoke_script['server_url'].__globals__, 'docker', run)
    assert smoke_script['server_url']('validation') == 'http://127.0.0.1:49152'


@pytest.mark.parametrize('running, binding, message', [
    (
        False,
        None,
        'exited.*exit code 1',
    ),
    (
        True,
        None,
        'did not publish port 8096/tcp',
    ),
    (
        True,
        {
            'HostIp': '192.0.2.1',
            'HostPort': '49152',
        },
        'published only on loopback',
    ),
])
def test_server_url_reports_startup_and_binding_failures(smoke_script, monkeypatch, running, binding, message):
    container = {
        'State': {
            'Running': running,
            'Status': 'running' if running else 'exited',
            'ExitCode': 0 if running else 1,
        },
        'NetworkSettings': {'Ports': {'8096/tcp': [binding]} if binding else {}},
    }
    run = Mock(return_value=json.dumps([container]))
    monkeypatch.setitem(smoke_script['server_url'].__globals__, 'docker', run)
    with pytest.raises(RuntimeError, match=message):
        smoke_script['server_url']('validation')


def test_docker_logs_preserve_standard_error(smoke_script, monkeypatch):
    result = subprocess.CompletedProcess('docker', 0, stdout='server output\n', stderr='startup error\n')
    monkeypatch.setattr(smoke_script['subprocess'], 'run', Mock(return_value=result))
    assert smoke_script['docker']('logs', 'validation') == 'server output\nstartup error'


def test_failed_docker_command_prints_diagnostics(smoke_script, monkeypatch, capsys):
    error = subprocess.CalledProcessError(125, 'docker', stderr='network setup failed')
    monkeypatch.setattr(smoke_script['subprocess'], 'run', Mock(side_effect=error))
    with pytest.raises(subprocess.CalledProcessError):
        smoke_script['docker']('run', 'validation')
    assert 'network setup failed' in capsys.readouterr().err
