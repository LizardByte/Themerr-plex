# -*- coding: utf-8 -*-

# lib imports
import pytest

# local imports
from Code import plex_api_helper


def test_all_themes_unlocked(section):
    field = 'theme'
    for item in section.all():
        assert not item.isLocked(field=field)


@pytest.mark.parametrize('lock', [
    False,  # verify the function pre-checks are working
    True,  # verify changing the lock status to True works
    False,  # verify changing the lock status to False works
])
def test_change_lock_status(section, lock):
    field = 'theme'
    for item in section.all():
        change_status = plex_api_helper.change_lock_status(item, field=field, lock=lock)
        assert change_status, 'change_lock_status did not return True'
        assert item.isLocked(field=field) == lock, 'Failed to change lock status to {}'.format(lock)
