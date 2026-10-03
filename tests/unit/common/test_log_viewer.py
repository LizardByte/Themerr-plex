"""Bounded log history, canonical logging channels, and privacy regression coverage."""

# standard imports
import logging
from unittest.mock import Mock

# lib imports
import pytest

# local imports
import common
from common import helpers, logger, log_viewer


def line(message='message', level='INFO', timestamp='2026-10-03 10:00:00.001'):
    return f'{timestamp} - {level:7s} :: MainThread : webapp : {message}\n'


@pytest.fixture
def logs_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(log_viewer.Paths, 'LOG_DIR', str(tmp_path))
    return tmp_path


@pytest.fixture
def session_capture(monkeypatch):
    capture = log_viewer._SessionLogHandler()
    monkeypatch.setattr(logger, '_session_handler', capture)
    try:
        yield capture
    finally:
        capture.close()


def session_record(message, name='themerr', level=logging.INFO):
    return logging.LogRecord(name, level, __file__, 1, message, (), None)


def test_session_pages_exclude_previous_runs_and_preserve_all_records_after_rotation(
        configured, logs_dir, session_capture, monkeypatch):
    (logs_dir / 'themerr.log').write_text(line('previous run'), encoding='utf-8')
    monkeypatch.setattr(logger, 'MAX_SIZE', 300)
    monkeypatch.setattr(logger, 'MAX_FILES', 1)
    monkeypatch.setattr(logger, '_init_hooks', Mock())
    monkeypatch.setattr(common, 'QUIET', True)
    names = [*logger.LOG_NAMES, 'uvicorn', 'uvicorn.error', 'uvicorn.access', 'schedule']
    original = {name: (logging.getLogger(name).handlers[:], logging.getLogger(name).level,
                       logging.getLogger(name).propagate) for name in names}
    try:
        logger.setup_loggers()
        for index in range(2501):
            logger.get_logger('themerr').info('session record %04d', index)
        assert 'session record 0000' not in ''.join(path.read_text(encoding='utf-8') for path in logs_dir.iterdir())
        records = []
        cursor = 0
        while True:
            result = log_viewer.session_snapshot(limit=1000, cursor=cursor)
            records.extend(result['entries'])
            assert len(result['entries']) <= 1000
            assert not result['truncated']
            assert result['unavailable'] == []
            cursor = result['cursor']
            if not result['has_more']:
                break
        assert len(records) == 2501
        assert records[0]['message'].endswith('session record 0000')
        assert records[-1]['message'].endswith('session record 2500')
        assert len({entry['id'] for entry in records}) == 2501
        assert 'previous run' not in str(records)
        logger.setup_loggers()
        assert logger._session_handler is session_capture
        logger.get_logger('yt-dlp').warning('new extractor warning')
        next_batch = log_viewer.session_snapshot(cursor=cursor)
        assert len(next_batch['entries']) == 1
        assert next_batch['entries'][0]['source'] == 'yt-dlp'
    finally:
        for name in names:
            target = logging.getLogger(name)
            logger._remove_handlers(target)
            target.handlers, target.level, target.propagate = original[name]


def test_session_source_filtering_and_byte_budget_make_progress(session_capture, monkeypatch):
    for name in ('themerr', 'uvicorn.error', 'yt-dlp', 'themerr', 'uvicorn.access'):
        session_capture.handle(session_record(f'{name} message', name))
    monkeypatch.setattr(log_viewer, 'MAX_READ_BYTES', 1)
    cursor, entries = 0, []
    for _ in range(5):
        result = log_viewer.session_snapshot('backend', limit=1, cursor=cursor)
        assert result['cursor'] > cursor
        cursor = result['cursor']
        entries.extend(result['entries'])
    assert [entry['source'] for entry in entries] == ['backend', 'backend']
    assert not result['has_more']
    assert log_viewer.session_snapshot(cursor=cursor)['entries'] == []
    assert log_viewer.session_snapshot(cursor=10**100)['entries'] == []
    assert log_viewer.session_snapshot(cursor=1)['cursor'] > 1


def test_session_history_masks_tracebacks_and_newly_blacklisted_secrets(session_capture, monkeypatch):
    monkeypatch.setattr(logger, '_BLACKLIST_WORDS', set())
    session_capture.handle(session_record('new-secret\nTraceback:\nX-Plex-Token=example_token', level=logging.ERROR))
    monkeypatch.setattr(logger, '_BLACKLIST_WORDS', {'new-secret'})
    result = log_viewer.session_snapshot()
    assert 'Traceback:' in result['entries'][0]['message']
    assert 'new-secret' not in result['entries'][0]['message']
    assert 'example_token' not in result['entries'][0]['message']
    session_capture.stream.seek(0)
    assert b'example_token' not in session_capture.stream.read()


def test_session_close_releases_storage_and_missing_storage_is_reported(session_capture, monkeypatch):
    session_capture.close()
    assert session_capture.stream.closed
    assert log_viewer.session_snapshot()['unavailable'] == list(logger.LOG_NAMES)
    monkeypatch.setattr(logger, '_session_handler', None)
    assert log_viewer.session_snapshot()['unavailable'] == list(logger.LOG_NAMES)


def test_failed_session_writes_keep_the_last_complete_record(session_capture, monkeypatch):
    session_capture.handle(session_record('complete record'))
    stream = session_capture.stream
    broken = Mock(wraps=stream)
    broken.write.side_effect = OSError('disk full')
    monkeypatch.setattr(session_capture, 'stream', broken)
    monkeypatch.setattr(session_capture, 'handleError', Mock())
    session_capture.handle(session_record('lost record'))
    result = log_viewer.session_snapshot()
    assert result['entries'][0]['message'].endswith('complete record')
    assert len(result['entries']) == 1
    assert result['unavailable'] == list(logger.LOG_NAMES)
    session_capture.handle(session_record('another record'))
    assert broken.write.call_count == 1


@pytest.mark.parametrize('source, limit, cursor', [('private', 1, 0), ('all', 2001, 0), ('all', 1, -1)])
def test_session_selection_is_validated(source, limit, cursor):
    with pytest.raises(ValueError):
        log_viewer.session_snapshot(source, limit, cursor)


def test_rotated_history_keeps_multiline_errors_and_merges_sources(logs_dir):
    (logs_dir / 'themerr.log.1').write_text(line('older', timestamp='2026-10-03 09:00:00'), encoding='utf-8')
    (logs_dir / 'themerr.log').write_text(
        line('failed', 'ERROR') + 'Traceback:\n  detail\nValueError: résumé\n', encoding='utf-8',
    )
    (logs_dir / 'backend.log').write_text(line('serving', timestamp='2026-10-03 09:30:00.000'), encoding='utf-8')
    result = log_viewer.snapshot()
    assert [entry['source'] for entry in result['entries']] == ['themerr', 'backend', 'themerr']
    assert result['entries'][-1]['message'] == 'webapp : failed\nTraceback:\n  detail\nValueError: résumé'
    assert result['entries'][-1]['level'] == 'ERROR'
    assert not result['truncated']
    assert result['unavailable'] == []
    selected = log_viewer.snapshot('themerr', limit=1)
    assert selected['entries'] == [result['entries'][-1]]
    assert selected['truncated']


def test_tail_reads_are_bounded_and_skip_partial_records(logs_dir, monkeypatch):
    (logs_dir / 'themerr.log').write_text('x' * 1024 + '\n' + line('Léon'), encoding='utf-8')
    monkeypatch.setattr(log_viewer, 'MAX_READ_BYTES', 100)
    result = log_viewer.snapshot('themerr')
    assert len(result['entries']) == 1
    assert result['entries'][0]['message'] == 'webapp : Léon'
    assert result['truncated']


def test_ids_survive_append_and_rotation(logs_dir):
    current = logs_dir / 'themerr.log'
    current.write_text(line('first'), encoding='utf-8')
    first = log_viewer.snapshot()['entries'][0]
    with current.open('a', encoding='utf-8') as stream:
        stream.write(line('second'))
    assert log_viewer.snapshot()['entries'][0] == first
    current.rename(logs_dir / 'themerr.log.1')
    current.write_text(line('third'), encoding='utf-8')
    result = log_viewer.snapshot()['entries']
    assert result[0] == first
    assert len({entry['id'] for entry in result}) == 3


def test_exact_tail_boundary_keeps_full_headers_and_ignores_incomplete_writes(logs_dir, monkeypatch):
    current = logs_dir / 'themerr.log'
    current.write_bytes((line('first') + line('second')).encode('utf-8'))
    monkeypatch.setattr(log_viewer, 'MAX_READ_BYTES', len(line('second').encode()))
    assert log_viewer.snapshot()['entries'][0]['message'] == 'webapp : second'
    monkeypatch.setattr(log_viewer, 'MAX_READ_BYTES', 1024)
    with current.open('a', encoding='utf-8') as stream:
        stream.write(line('partial').rstrip('\n'))
    assert len(log_viewer.snapshot()['entries']) == 2
    with current.open('a', encoding='utf-8') as stream:
        stream.write('\n')
    assert len(log_viewer.snapshot()['entries']) == 3


def test_empty_and_unreadable_sources(logs_dir, monkeypatch):
    assert log_viewer.snapshot() == {'entries': [], 'unavailable': [], 'truncated': False}
    (logs_dir / 'backend.log').write_text(line('backend record'), encoding='utf-8')
    read = log_viewer._read_file

    def denied(path, source, budget):
        if source == 'backend':
            raise PermissionError('private server path')
        return read(path, source, budget)

    monkeypatch.setattr(log_viewer, '_read_file', denied)
    assert log_viewer.snapshot()['unavailable'] == ['backend']


@pytest.mark.parametrize('source', [
    '../config.ini', '/config.ini', r'C:\config.ini', r'\\server\share\config.ini',
    'themerr/../config.ini', 'themerr.log', 'themerr.log.1', 'themerr%2flog', 'themerr\x00',
])
def test_request_source_never_becomes_a_filesystem_path(source, monkeypatch):
    def unexpected_lookup(*args):
        pytest.fail('A request-provided path reached the filesystem')

    monkeypatch.setattr(log_viewer, 'resolve_file_path', unexpected_lookup)
    with pytest.raises(ValueError):
        log_viewer.snapshot(source)


def test_log_reader_uses_only_fixed_names_and_reports_blocked_files(logs_dir, monkeypatch):
    calls = []

    def guarded_path(directory, filename):
        assert directory == str(logs_dir)
        calls.append(filename)
        if filename == 'backend.log':
            raise PermissionError('Symlink target is outside the log directory')
        raise FileNotFoundError

    monkeypatch.setattr(log_viewer, 'resolve_file_path', guarded_path)
    result = log_viewer.snapshot('backend')
    assert calls == ['backend.log']
    assert result['entries'] == []
    assert result['unavailable'] == ['backend']
    calls.clear()
    log_viewer.snapshot('themerr')
    assert calls == ['themerr.log', *(f'themerr.log.{index}' for index in range(1, logger.MAX_FILES + 1))]


def test_file_reader_enforces_path_policy_for_direct_callers(logs_dir):
    private = logs_dir.parent / 'private.log'
    private.write_text(line('private server data'), encoding='utf-8')
    with pytest.raises(ValueError):
        log_viewer._read_file('../private.log', 'themerr', 1000)
    with pytest.raises(ValueError):
        log_viewer._read_file(str(private), 'themerr', 1000)


@pytest.mark.parametrize('source, limit', [('../private', 10), ('common', 10), ('all', 0), ('all', 2001)])
def test_only_fixed_log_sources_and_bounded_limits_are_accepted(source, limit):
    with pytest.raises(ValueError):
        log_viewer.snapshot(source, limit)


def test_privacy_applies_to_formatted_exceptions_and_existing_files(logs_dir, monkeypatch):
    monkeypatch.setattr(logger, '_BLACKLIST_WORDS', {'supersecret'})
    formatter = logger.PrivateFormatter('%(message)s')
    try:
        raise ValueError('supersecret X-Plex-Token=abc-def_123 alice@example.com 8.8.8.8')
    except ValueError:
        import sys
        entry = logging.LogRecord('themerr', logging.ERROR, __file__, 1, '%(secret)s',
                                  ({'secret': 'supersecret'},), sys.exc_info())
    masked = formatter.format(entry)
    assert 'ValueError' in masked
    for secret in ('supersecret', 'abc-def_123', 'alice@example.com', '8.8.8.8'):
        assert secret not in masked
    (logs_dir / 'themerr.log').write_text(line('supersecret', 'ERROR') + 'x-plex-token=abc-def_123\n', encoding='utf-8')
    message = log_viewer.snapshot()['entries'][0]['message']
    assert 'supersecret' not in message
    assert 'abc-def_123' not in message


def test_three_channels_route_application_uvicorn_scheduler_and_ytdlp_once(configured, logs_dir, monkeypatch):
    monkeypatch.setattr(common, 'QUIET', True)
    monkeypatch.setattr(common, 'DEV', False)
    monkeypatch.setattr(common, 'DEBUG', False)
    monkeypatch.setattr(logger, '_init_hooks', Mock())
    touched = [*logger.LOG_NAMES, 'uvicorn', 'uvicorn.error', 'uvicorn.access', 'schedule']
    original = {name: (logging.getLogger(name).handlers[:], logging.getLogger(name).level,
                       logging.getLogger(name).propagate) for name in touched}
    try:
        logger.setup_loggers()
        logger.setup_loggers()  # Reconfiguration must not duplicate or retain old file handlers.
        for name in ('common.webapp', 'common.helpers', 'plex.plexapi', 'themerr.general', 'youtube.youtube_dl'):
            assert logger.get_logger(name) is logging.getLogger('themerr')
            assert helpers.get_logger(name) is logger.get_logger(name)
            logger.get_logger(name).info('application %s', name)
        logging.getLogger('uvicorn.error').info('backend startup')
        logging.getLogger('uvicorn.access').info('backend request')
        logging.getLogger('schedule').info('scheduled task')
        extractor = logger.YtDlpLogger()
        extractor.debug('[download] extractor progress')
        extractor.debug('[debug] hidden debug')
        extractor.warning('extractor warning')
        extractor.error('extractor failure')
        assert sorted(path.name for path in logs_dir.glob('*.log')) == ['backend.log', 'themerr.log', 'yt-dlp.log']
        assert (logs_dir / 'backend.log').read_text(encoding='utf-8').count('backend startup') == 1
        assert (logs_dir / 'backend.log').read_text(encoding='utf-8').count('backend request') == 1
        application = (logs_dir / 'themerr.log').read_text(encoding='utf-8')
        assert application.count('application ') == 5
        assert application.count('scheduled task') == 1
        extractor_log = (logs_dir / 'yt-dlp.log').read_text(encoding='utf-8')
        assert 'INFO' in extractor_log
        assert 'extractor progress' in extractor_log
        assert 'WARNING' in extractor_log
        assert 'ERROR' in extractor_log
        assert 'hidden debug' not in extractor_log
    finally:
        for name in touched:
            target = logging.getLogger(name)
            for handler in target.handlers[:]:
                target.removeHandler(handler)
                handler.close()
            target.handlers, target.level, target.propagate = original[name]


@pytest.mark.parametrize('path, status, expected', [
    ('/api/logs?source=all&limit=1000', 200, False), ('/api/logs', 500, True),
    ('/api/logs', 401, True), ('/api/tasks', 200, True), ('/logs', 200, True),
])
def test_access_logs_retain_failures_but_exclude_successful_viewer_polls(path, status, expected):
    entry = logging.LogRecord('uvicorn.access', logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
                              ('127.0.0.1:1234', 'GET', path, '1.1', status), None)
    assert logger.LogPollFilter().filter(entry) is expected
