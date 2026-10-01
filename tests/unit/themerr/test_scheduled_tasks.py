"""Scheduling behavior without a live background loop."""

from threading import Event
from unittest.mock import Mock

from themerr import scheduled_tasks


def test_run_threaded():
    done = Event()
    thread = scheduled_tasks.run_threaded(target=done.set)
    thread.join(timeout=2)
    assert done.is_set()
    assert not thread.is_alive()
    assert thread.daemon


def test_scheduled_task_logs_start_and_finish(monkeypatch):
    started, finished = Mock(), Mock()
    monkeypatch.setattr(scheduled_tasks.log, 'info', started)
    job = scheduled_tasks.run_threaded(target=finished, task_name='Dashboard refresh')
    job.join(timeout=2)

    finished.assert_called_once_with()
    assert started.call_args_list[0].args == ('Scheduled task started: %s', 'Dashboard refresh')
    assert started.call_args_list[1].args[:2] == ('Scheduled task finished: %s (%.1f seconds)', 'Dashboard refresh')


def test_scheduled_task_failure_is_logged_and_thread_exits(monkeypatch):
    error = Mock()
    monkeypatch.setattr(scheduled_tasks.log, 'exception', error)
    job = scheduled_tasks.run_threaded(target=Mock(side_effect=RuntimeError('failed')),
                                       task_name='Theme scan and queue')
    job.join(timeout=2)

    assert not job.is_alive()
    assert error.call_args.args[:2] == ('Scheduled task failed: %s (%.1f seconds)', 'Theme scan and queue')


def test_schedule_loop(monkeypatch):
    run_all = Mock()
    pending = Mock()

    def sleep(seconds):
        assert seconds == 1
        run_all.assert_called_once()
        pending.assert_called_once()
        raise RuntimeError('stop')

    monkeypatch.setattr(scheduled_tasks.time, 'sleep', sleep)
    monkeypatch.setattr(scheduled_tasks.schedule, 'run_all', run_all)
    monkeypatch.setattr(scheduled_tasks.schedule, 'run_pending', pending)
    try:
        scheduled_tasks.schedule_loop()
    except RuntimeError:
        pass
    run_all.assert_called_once()
    pending.assert_called_once()


def test_setup_scheduling(configured, monkeypatch):
    started = Mock()
    monkeypatch.setattr(scheduled_tasks, 'run_threaded', started)
    scheduled_tasks.schedule.clear()
    configured['Themerr']['BOOL_THEMERR_ENABLED'] = True
    scheduled_tasks.setup_scheduling()
    assert len(scheduled_tasks.schedule.jobs) == 2
    assert all(job.job_func.keywords['daemon'] for job in scheduled_tasks.schedule.jobs)
    started.assert_called_once_with(target=scheduled_tasks.schedule_loop, daemon=True)
    scheduled_tasks.schedule.clear()

    configured['Themerr']['BOOL_THEMERR_ENABLED'] = False
    scheduled_tasks.setup_scheduling()
    assert len(scheduled_tasks.schedule.jobs) == 1
    scheduled_tasks.schedule.clear()
