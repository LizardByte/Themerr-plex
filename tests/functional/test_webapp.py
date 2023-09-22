# -*- coding: utf-8 -*-
# lib imports
import pytest


def test_home(test_client):
    """
    WHEN the '/' page is requested (GET)
    THEN check that the response is valid

    Repeat for '/home'
    """
    try:
        response = test_client.get('/')
    except AttributeError:
        pytest.skip("cannot access Plex token/server")
    else:
        assert response.status_code == 200

        response = test_client.get('/home')
        assert response.status_code == 200


def test_image(test_client):
    """
    WHEN the '/favicon.ico' file is requested (GET)
    THEN check that the response is valid
    THEN check the content type is 'image/vnd.microsoft.icon'
    """
    response = test_client.get('favicon.ico')
    assert response.status_code == 200
    assert response.content_type == 'image/vnd.microsoft.icon'


def test_status(test_client):
    """
    WHEN the '/status' page is requested (GET)
    THEN check that the response is valid
    """
    response = test_client.get('/status')
    assert response.status_code == 200
    assert response.content_type == 'application/json'
