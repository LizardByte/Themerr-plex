"""CLI argument handling and startup orchestration without launching services."""

# standard imports
import argparse
import sys
from unittest.mock import Mock

# lib imports
import pytest

# local imports
import common
from common import helpers
from common import threads
from plex import plexapi
from themerr import scheduled_tasks
import themerr_plex


def test_int_range():
    bounded = themerr_plex.IntRange(21, 65535)
    assert bounded('9494') == 9494
    with pytest.raises(argparse.ArgumentTypeError):
        bounded('20')


def test_help_uses_application_translation(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['themerr_plex.py', '--help'])
    monkeypatch.setattr(themerr_plex, '_', lambda message: f'translated: {message}')

    with pytest.raises(SystemExit) as result:
        themerr_plex.main()

    assert result.value.code == 0
    assert 'translated: Show this help message and exit' in capsys.readouterr().out


@pytest.mark.parametrize('healthy,exit_code', [(True, 0), (False, 1)])
def test_healthcheck_exit(monkeypatch, healthy, exit_code):
    monkeypatch.setattr(sys, 'argv', ['themerr_plex.py', '--docker_healthcheck'])
    monkeypatch.setattr(helpers, 'docker_healthcheck', lambda: healthy)
    with pytest.raises(SystemExit) as result:
        themerr_plex.main()
    assert result.value.code == exit_code


def test_main_starts_services(configured, monkeypatch):
    configured['General']['SYSTEM_TRAY'] = False
    monkeypatch.setattr(sys, 'argv', ['themerr_plex.py', '--nolaunch', '--port', '9495'])
    initialized = Mock(return_value=True)
    monkeypatch.setattr(common, 'initialize', initialized)
    worker = Mock()
    worker.start = Mock()
    monkeypatch.setattr(threads, 'run_in_thread', Mock(return_value=worker))
    monkeypatch.setattr(plexapi, 'start_queue_threads', Mock())
    monkeypatch.setattr(plexapi, 'plex_listener', Mock())
    monkeypatch.setattr(scheduled_tasks, 'setup_scheduling', Mock())
    monkeypatch.setattr(themerr_plex, 'wait', Mock())

    themerr_plex.main()

    initialized.assert_called_once()
    worker.start.assert_called_once()
    plexapi.start_queue_threads.assert_called_once()
    plexapi.plex_listener.assert_called_once()
    scheduled_tasks.setup_scheduling.assert_called_once()
    assert configured['Network']['HTTP_PORT'] == 9495


def test_wait_shutdown(monkeypatch):
    monkeypatch.setattr(common, 'SIGNAL', 'shutdown')
    stopped = Mock()
    monkeypatch.setattr(common, 'stop', stopped)
    themerr_plex.wait()
    stopped.assert_called_once_with()


def test_wait_keyboard_interrupt(monkeypatch):
    monkeypatch.setattr(common, 'SIGNAL', None)
    monkeypatch.setattr(themerr_plex.time, 'sleep', Mock(side_effect=KeyboardInterrupt))
    stopped = Mock()
    monkeypatch.setattr(common, 'stop', stopped)
    themerr_plex.wait()
    stopped.assert_called_once_with()


def test_console_password_reset_invalidates_sessions_without_starting_services(configured, monkeypatch, capsys):
    from werkzeug.security import check_password_hash
    from common import admin
    monkeypatch.setattr(admin, 'HASH_METHOD', 'scrypt:16384:8:1')
    previous = admin._save('admin', 'the original test passphrase')
    monkeypatch.setattr(sys, 'argv', ['themerr_plex.py', '--reset-admin-password'])
    monkeypatch.setattr(common, 'initialize', Mock(return_value=True))
    monkeypatch.setattr(themerr_plex.getpass, 'getpass', lambda prompt: 'the replacement test passphrase')
    start = Mock()
    monkeypatch.setattr(threads, 'run_in_thread', start)
    themerr_plex.main()
    current = admin.account()
    assert current['username'] == previous['username']
    assert current['revision'] != previous['revision']
    assert check_password_hash(current['password_hash'], 'the replacement test passphrase')
    assert 'replacement test passphrase' not in capsys.readouterr().out
    start.assert_not_called()
