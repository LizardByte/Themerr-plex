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


def test_get_user_info(plex_token):
    assert plex_api_helper.get_user_info(token=plex_token)


def test_get_user_info_invalid_token():
    assert not plex_api_helper.get_user_info(token='invalid_token')


def test_is_server_owner(plex_token):
    user = plex_api_helper.get_user_info(token=plex_token)
    assert plex_api_helper.is_server_owner(user=user)


def test_is_not_server_owner():
    assert plex_api_helper.is_server_owner(user={}) is None
