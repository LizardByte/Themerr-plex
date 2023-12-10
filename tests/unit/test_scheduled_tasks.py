# -*- coding: utf-8 -*-

# standard imports
import time

# local imports
from Code import scheduled_tasks


def test_run_threaded():
    def hello_world():
        time.sleep(10)
        return 'Hello, world!'

    test_thread = scheduled_tasks.run_threaded(target=hello_world, daemon=True)
    assert test_thread.is_alive()

    test_thread.join()
    assert not test_thread.is_alive()


def test_schedule_loop():
    test_thread = scheduled_tasks.run_threaded(target=scheduled_tasks.schedule_loop, daemon=True)
    assert test_thread.is_alive()


def test_setup_scheduling():
    scheduled_tasks.setup_scheduling()
    assert scheduled_tasks.schedule.jobs
