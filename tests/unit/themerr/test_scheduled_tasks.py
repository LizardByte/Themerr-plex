"""Scheduling behavior without a live background loop."""

from threading import Event
from unittest.mock import Mock

from themerr import scheduled_tasks


def test_run_threaded():
    done = Event()
    thread = scheduled_tasks.run_threaded(target=done.set, daemon=True)
    thread.join(timeout=2)
    assert done.is_set()
    assert not thread.is_alive()


def test_schedule_loop(monkeypatch):
    run_all = Mock()
    pending = Mock()
    sleeps = iter([None, RuntimeError('stop')])

    def sleep(_):
        result = next(sleeps)
        if result:
            raise result

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
    started.assert_called_once_with(target=scheduled_tasks.schedule_loop, daemon=True)
    scheduled_tasks.schedule.clear()

    configured['Themerr']['BOOL_THEMERR_ENABLED'] = False
    scheduled_tasks.setup_scheduling()
    assert len(scheduled_tasks.schedule.jobs) == 1
    scheduled_tasks.schedule.clear()
