# -*- coding: utf-8 -*-

# standard imports
import os

# lib imports
import pytest

# local imports
from Code import webapp


@pytest.fixture(scope='function')
def remove_themerr_db_cache_file():
    _backup_file_name = "{}.bak".format(webapp.database_cache_file)

    # rename the file, so it is not found
    if os.path.exists(webapp.database_cache_file):
        os.rename(webapp.database_cache_file, _backup_file_name)
    yield

    # rename the file back
    if os.path.exists(_backup_file_name):
        os.rename(_backup_file_name, webapp.database_cache_file)


def test_home_login_disabled(test_client_login_disabled):
    """
    WHEN the '/' page is requested (GET)
    THEN check that the response is valid

    Repeat for '/home'
    """
    try:
        response = test_client_login_disabled.get('/')
    except AttributeError:
        pytest.skip("cannot access Plex token/server")
    else:
        assert response.status_code == 200

        response = test_client_login_disabled.get('/home')
        assert response.status_code == 200

        assert 'id="section_' in response.data.decode('utf-8')


def test_home(test_client):
    """
    WHEN the '/' page is requested (GET)
    THEN check that the response is a redirect

    Repeat for '/home'
    """
    try:
        response = test_client.get('/')
    except AttributeError:
        pytest.skip("cannot access Plex token/server")
    else:
        assert response.status_code == 302

        response = test_client.get('/home')
        assert response.status_code == 302


def test_home_without_cache_login_disabled(remove_themerr_db_cache_file, test_client_login_disabled):
    """
    WHEN the '/' page is requested (GET)
    THEN check that the response is valid
    """
    try:
        response = test_client_login_disabled.get('/')
    except AttributeError:
        pytest.skip("cannot access Plex token/server")
    else:
        assert response.status_code == 200

        assert 'Database is being cached' in response.data.decode('utf-8')


def test_home_without_cache(remove_themerr_db_cache_file, test_client):
    """
    WHEN the '/' page is requested (GET)
    THEN check that the response is a redirect
    """
    try:
        response = test_client.get('/')
    except AttributeError:
        pytest.skip("cannot access Plex token/server")
    else:
        assert response.status_code == 302


def test_image_login_disabled(test_client_login_disabled):
    """
    WHEN the '/favicon.ico' file is requested (GET)
    THEN check that the response is valid
    THEN check the content type is 'image/vnd.microsoft.icon'
    """
    response = test_client_login_disabled.get('favicon.ico')
    assert response.status_code == 200
    assert response.content_type == 'image/vnd.microsoft.icon'


def test_image(test_client):
    """
    WHEN the '/favicon.ico' file is requested (GET)
    THEN check that the response is a redirect
    """
    response = test_client.get('favicon.ico')
    assert response.status_code == 302


def test_status_no_login(test_client_login_disabled):
    """
    WHEN the '/status' page is requested (GET)
    THEN check that the response is valid
    """
    response = test_client_login_disabled.get('/status')
    assert response.status_code == 200
    assert response.content_type == 'application/json'


def test_status(test_client):
    """
    WHEN the '/status' page is requested (GET)
    THEN check that the response is a redirect
    """
    response = test_client.get('/status')
    assert response.status_code == 302
