# -*- coding: utf-8 -*-
# standard imports
from functools import partial
import os
import sys
import time

# lib imports
import plexapi
from plexapi.exceptions import NotFound
from plexapi.server import PlexServer
from plexhints.agent_kit import Agent
import pytest
import requests

# add Contents directory to the system path
if os.path.isdir('Contents'):
    sys.path.append('Contents')

    # local imports
    from Code import constants
    from Code import Themerr
    from Code import webapp
else:
    raise Exception('Contents directory not found')

# plex server setup
SERVER_BASEURL = plexapi.CONFIG.get("auth.server_baseurl")
SERVER_TOKEN = plexapi.CONFIG.get("auth.server_token")


def wait_for_themes(movies):
    # ensure library is not refreshing
    while movies.refreshing:
        time.sleep(1)

    # wait for themes to be uploaded
    timer = 0
    with_themes = 0
    total = len(movies.all())
    while timer < 180 and with_themes < total:
        with_themes = 0
        try:
            for item in movies.all():
                if item.theme:
                    with_themes += 1
        except requests.ReadTimeout:
            time.sleep(10)  # try to recover from ReadTimeout (hit api limit?)
        else:
            time.sleep(3)
            timer += 3

    assert with_themes == total, (
        "Not all themes were uploaded in time, themes uploaded: {}/{}".format(with_themes, total))


# basic fixtures
@pytest.fixture
def agent():
    # type: () -> Agent
    return Themerr()


@pytest.fixture
def test_client(scope='function'):
    """Create a test client for testing webapp endpoints"""
    app = webapp.app
    app.config['TESTING'] = True

    client = app.test_client()

    # Create a test client using the Flask application configured for testing
    with client as test_client:
        # Establish an application context
        with app.app_context():
            yield test_client  # this is where the testing happens!


# plex server fixtures
@pytest.fixture(scope="session")
def plugin_logs():
    # list contents of the plugin logs directory
    plugin_logs = os.listdir(os.environ['PLEX_PLUGIN_LOG_PATH'])

    yield plugin_logs


# plex server fixtures
@pytest.fixture(scope="session")
def plugin_log_file():
    # the primary plugin log file
    plugin_log_file = os.path.join(os.environ['PLEX_PLUGIN_LOG_PATH'], "{}.log".format(constants.plugin_identifier))

    yield plugin_log_file


@pytest.fixture(scope="session")
def sess():
    session = requests.Session()
    session.request = partial(session.request, timeout=120)
    return session


@pytest.fixture(scope="session")
def plex(request, sess):
    assert SERVER_BASEURL, "Required SERVER_BASEURL not specified."

    return PlexServer(SERVER_BASEURL, SERVER_TOKEN, session=sess)


@pytest.fixture(scope="session")
def movies_new_agent(plex):
    movies = plex.library.section("Movies")
    wait_for_themes(movies=movies)
    return movies


@pytest.fixture(scope="session")
def movies_imdb_agent(plex):
    movies = plex.library.section("Movies-imdb")
    wait_for_themes(movies=movies)
    return movies


@pytest.fixture(scope="session")
def movies_themoviedb_agent(plex):
    movies = plex.library.section("Movies-tmdb")
    wait_for_themes(movies=movies)
    return movies


@pytest.fixture(scope="session")
def collection_new_agent(plex, movies_new_agent, movie_new_agent):
    try:
        return movies_new_agent.collection("Test Collection")
    except NotFound:
        return plex.createCollection(
            title="Test Collection",
            section=movies_new_agent,
            items=movie_new_agent
        )


@pytest.fixture(scope="session")
def collection_imdb_agent(plex, movies_imdb_agent, movie_imdb_agent):
    try:
        return movies_imdb_agent.collection("Test Collection")
    except NotFound:
        return plex.createCollection(
            title="Test Collection",
            section=movies_imdb_agent,
            items=movie_imdb_agent
        )


@pytest.fixture(scope="session")
def collection_themoviedb_agent(plex, movies_themoviedb_agent, movie_themoviedb_agent):
    try:
        return movies_themoviedb_agent.collection("Test Collection")
    except NotFound:
        return plex.createCollection(
            title="Test Collection",
            section=movies_themoviedb_agent,
            items=movie_themoviedb_agent
        )
