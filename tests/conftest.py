# -*- coding: utf-8 -*-
# standard imports
from functools import partial
import os
import sys
import time

# lib imports
import plexapi
from plexapi.exceptions import NotFound
from plexapi.myplex import MyPlexAccount
from plexapi.server import PlexServer
from plexhints.agent_kit import Agent
from plexhints.core_kit import PLUGIN_LOGS_PATH
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
MYPLEX_USERNAME = plexapi.CONFIG.get("auth.myplex_username")
MYPLEX_PASSWORD = plexapi.CONFIG.get("auth.myplex_password")
SERVER_TOKEN = plexapi.CONFIG.get("auth.server_token")

TEST_AUTHENTICATED = "authenticated"
TEST_ANONYMOUSLY = "anonymously"
ANON_PARAM = pytest.param(TEST_ANONYMOUSLY, marks=pytest.mark.anonymous)
AUTH_PARAM = pytest.param(TEST_AUTHENTICATED, marks=pytest.mark.authenticated)


BASE_DIR_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pytest_generate_tests(metafunc):
    if "plex" in metafunc.fixturenames:
        if (
            "account" in metafunc.fixturenames
            or TEST_AUTHENTICATED in metafunc.definition.keywords
        ):
            metafunc.parametrize("plex", [AUTH_PARAM], indirect=True)
        else:
            metafunc.parametrize("plex", [ANON_PARAM, AUTH_PARAM], indirect=True)
    elif "account" in metafunc.fixturenames:
        metafunc.parametrize("account", [AUTH_PARAM], indirect=True)


def pytest_runtest_setup(item):
    if "client" in item.keywords and not item.config.getvalue("client"):
        return pytest.skip("Need --client option to run.")
    if TEST_AUTHENTICATED in item.keywords and not (MYPLEX_USERNAME and MYPLEX_PASSWORD or SERVER_TOKEN):
        return pytest.skip(
            "You have to specify MYPLEX_USERNAME and MYPLEX_PASSWORD or SERVER_TOKEN to run authenticated tests"
        )
    if TEST_ANONYMOUSLY in item.keywords and (MYPLEX_USERNAME and MYPLEX_PASSWORD or SERVER_TOKEN):
        return pytest.skip(
            "Anonymous tests should be ran on unclaimed server, without providing MYPLEX_USERNAME and "
            "MYPLEX_PASSWORD or SERVER_TOKEN"
        )


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
    plugin_logs = os.listdir(PLUGIN_LOGS_PATH)

    yield plugin_logs


# plex server fixtures
@pytest.fixture(scope="session")
def plugin_log_file():
    # the primary plugin log file
    plugin_log_file = os.path.join(PLUGIN_LOGS_PATH, "{}.log".format(constants.plugin_identifier))

    yield plugin_log_file


@pytest.fixture(scope="session")
def sess():
    session = requests.Session()
    session.request = partial(session.request, timeout=120)
    return session


@pytest.fixture(scope="session")
def plex(request, sess):
    assert SERVER_BASEURL, "Required SERVER_BASEURL not specified."

    if request.param == TEST_AUTHENTICATED:
        token = MyPlexAccount(session=sess).authenticationToken
    else:
        token = None
    return PlexServer(SERVER_BASEURL, token, session=sess)


@pytest.fixture()
def movies_new_agent(plex):
    movies = plex.library.section("Movies-new-agent")
    wait_for_themes(movies=movies)
    return movies


@pytest.fixture()
def movies_imdb_agent(plex):
    movies = plex.library.section("Movies-imdb-agent")
    wait_for_themes(movies=movies)
    return movies


@pytest.fixture()
def movies_themoviedb_agent(plex):
    movies = plex.library.section("Movies-themoviedb-agent")
    wait_for_themes(movies=movies)
    return movies


@pytest.fixture()
def collection_new_agent(plex, movies_new_agent, movie_new_agent):
    try:
        return movies_new_agent.collection("Test Collection")
    except NotFound:
        return plex.createCollection(
            title="Test Collection",
            section=movies_new_agent,
            items=movie_new_agent
        )


@pytest.fixture()
def collection_imdb_agent(plex, movies_imdb_agent, movie_imdb_agent):
    try:
        return movies_imdb_agent.collection("Test Collection")
    except NotFound:
        return plex.createCollection(
            title="Test Collection",
            section=movies_imdb_agent,
            items=movie_imdb_agent
        )


@pytest.fixture()
def collection_themoviedb_agent(plex, movies_themoviedb_agent, movie_themoviedb_agent):
    try:
        return movies_themoviedb_agent.collection("Test Collection")
    except NotFound:
        return plex.createCollection(
            title="Test Collection",
            section=movies_themoviedb_agent,
            items=movie_themoviedb_agent
        )
