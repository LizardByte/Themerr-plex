"""Application initialization and shutdown without spawning processes."""

# standard imports
import os
from unittest.mock import Mock

# lib imports
import pytest

# local imports
import common
from common import tray_icon


def test_initialize_once(configured, monkeypatch, tmp_path):
    monkeypatch.setattr(common, '_INITIALIZED', False)
    monkeypatch.setattr(common, 'DEBUG', False)
    monkeypatch.setattr(common, 'QUIET', True)
    monkeypatch.setattr(common.config, 'create_config', lambda config_file: configured)
    monkeypatch.setattr(common.helpers, 'check_folder_writable', lambda **_: (str(tmp_path), True))
    blacklist = Mock()
    setup = Mock()
    monkeypatch.setattr(common.logger, 'blacklist_config', blacklist)
    monkeypatch.setattr(common.logger, 'setup_loggers', setup)

    configured['Network']['HTTP_PORT'] = 1
    assert common.initialize(str(tmp_path / 'config.ini')) is True
    assert configured['Network']['HTTP_PORT'] == 9494
    assert common.CONFIG_FILE == str(tmp_path / 'config.ini')
    blacklist.assert_called_once_with(config=configured)
    setup.assert_called_once()
    assert common.initialize(str(tmp_path / 'config.ini')) is False


def test_initialize_error(monkeypatch):
    monkeypatch.setattr(common.config, 'create_config', Mock(side_effect=ValueError('corrupt')))
    with pytest.raises(SystemExit, match='corrupted config'):
        common.initialize('invalid.ini')


def test_stop_and_restart(monkeypatch):
    from common import webapp
    end = Mock()
    launch = Mock()
    shutdown = Mock()
    exit_process = Mock(side_effect=lambda code: (_ for _ in ()).throw(SystemExit(code)))
    monkeypatch.setattr(tray_icon, 'tray_end', end)
    monkeypatch.setattr(common.subprocess, 'Popen', launch)
    monkeypatch.setattr(common.logger, 'shutdown', shutdown)
    stopped = Mock()
    monkeypatch.setattr(webapp, 'stop_webapp', stopped)
    calls = Mock()
    calls.attach_mock(stopped, 'stop_server')
    calls.attach_mock(launch, 'launch_replacement')
    monkeypatch.setattr(common.os, '_exit', exit_process)
    monkeypatch.setattr(common.definitions.Modes, 'FROZEN', False)
    monkeypatch.setattr(common.sys, 'argv', ['main.py', '--quiet'])

    with pytest.raises(SystemExit) as exit_info:
        common.stop(exit_code=3, restart=True)
    assert exit_info.value.code == 3
    assert [call[0] for call in calls.mock_calls[:2]] == ['stop_server', 'launch_replacement']
    assert launch.call_args.kwargs['args'][-2:] == ['--quiet', '--nolaunch']
    end.assert_called_once()
    shutdown.assert_called_once()
    exit_process.assert_called_once_with(3)

    launch.reset_mock()
    monkeypatch.setattr(common.sys, 'argv', ['scripts/run_dev.py', '--nolaunch'])
    with pytest.raises(SystemExit):
        common.stop(restart=True)
    assert launch.call_args.kwargs['args'][1] == os.path.abspath('scripts/run_dev.py')

    launch.reset_mock()
    with pytest.raises(SystemExit):
        common.stop(exit_code=0)
    launch.assert_not_called()
    assert exit_process.call_args.args == (0,)
