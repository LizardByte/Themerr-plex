"""Log filters mask credentials and public addresses."""

# standard imports
import logging
import threading
from unittest.mock import Mock

# local imports
from common import logger
import common


def record(message, args=()):
    return logging.LogRecord('test', logging.INFO, __file__, 1, message, args, None)


def test_blacklist_and_filters(monkeypatch):
    monkeypatch.setattr(logger, 'LOG_BLACKLIST', ['enabled'])
    monkeypatch.setattr(logger, '_BLACKLIST_WORDS', set())
    logger.blacklist_config({'Plex': {'PLEX_TOKEN': 'supersecret', 'SHORT_TOKEN': 'x'}})
    entry = record('token supersecret', ('supersecret',))
    assert logger.BlacklistFilter().filter(entry)
    assert 'supersecret' not in entry.msg
    assert 'supersecret' not in entry.args

    entry = record('Email alice@example.com and IP 8.8.8.8')
    assert logger.EmailFilter().filter(entry)
    assert logger.PublicIPFilter().filter(entry)
    assert 'alice@example.com' not in entry.msg
    assert '8.8.8.8' not in entry.msg
    entry = record('X-Plex-Token=abcdef123')
    assert logger.PlexTokenFilter().filter(entry)
    assert 'abcdef123' not in entry.msg


def test_thread_and_logger():
    assert logger.NoThreadFilter('other').filter(record('message'))
    assert not logger.NoThreadFilter('MainThread').filter(record('message'))
    assert logger.get_logger('themerr-test') is logging.getLogger('themerr-test')


def test_logger_setup(configured, monkeypatch, tmp_path):
    monkeypatch.setattr(logger.definitions.Paths, 'LOG_DIR', str(tmp_path))
    monkeypatch.setattr(common, 'QUIET', False)
    monkeypatch.setattr(common, 'DEV', False)
    monkeypatch.setattr(logger, '_init_hooks', Mock())

    target = logger.init_logger(logger.app_name)
    assert any(isinstance(handler, logging.StreamHandler) for handler in target.handlers)
    assert any(isinstance(handler, logger.handlers.RotatingFileHandler) for handler in target.handlers)
    assert all(handler.filters for handler in target.handlers)

    configured['Logging']['DEBUG_LOGGING'] = True
    monkeypatch.setattr(common, 'DEBUG', True)
    target = logger.init_logger(logger.app_name)
    assert target.level == logging.DEBUG
    logger._init_hooks.assert_called()
    for handler in target.handlers:
        handler.close()
        target.removeHandler(handler)


def test_setup_loggers_and_listener(monkeypatch):
    initialized = []
    monkeypatch.setattr(logger, 'init_logger', lambda log_name: initialized.append(log_name))
    logger.setup_loggers()
    assert logger.app_name in initialized
    assert 'werkzeug' in initialized

    target = logging.getLogger('listener-test')
    monkeypatch.setattr(logger, 'queue', False)
    with logger.listener(target):
        pass

    calls = []

    class FakeListener:
        def __init__(self, *_):
            pass

        def start(self):
            calls.append('start')

        def stop(self):
            calls.append('stop')

    monkeypatch.setattr(logger, 'queue', object())
    monkeypatch.setattr(logger, 'QueueListener', FakeListener)
    with logger.listener(target):
        assert calls == ['start']
    assert calls == ['start', 'stop']

    target.addHandler(logging.NullHandler())
    thread_name = threading.current_thread().name
    try:
        logger.init_multiprocessing(target)
        assert len(target.handlers) == 1
        assert isinstance(target.handlers[0], logger.QueueHandler)
    finally:
        threading.current_thread().name = thread_name
        for handler in target.handlers[:]:
            target.removeHandler(handler)
