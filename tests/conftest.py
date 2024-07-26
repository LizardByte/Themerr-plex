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
pytest.root_dir = root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pytest.contents_dir = contents_dir = os.path.join(root_dir, 'Contents')
if os.path.isdir(contents_dir):
    sys.path.append(contents_dir)

    # local imports
    from Code import constants
    from Code import Themerr, ThemerrMovies, ThemerrTvShows
    from Code import themerr_db_helper
    from Code import webapp
else:
    raise Exception('Contents directory not found')

# plex server setup
SERVER_BASEURL = plexapi.CONFIG.get("auth.server_baseurl")
SERVER_TOKEN = plexapi.CONFIG.get("auth.server_token")

# constants
MOVIE_SECTIONS = ["Movies", "Movies-imdb", "Movies-tmdb"]
TV_SHOW_SECTIONS = ["TV Shows", "TV Shows-tmdb", "TV Shows-tvdb"]


def wait_for_file(file_path, timeout=300):
    # type: (str, int) -> None
    found = False
    count = 0
    while not found and count < timeout:  # plugin takes a little while to start on macOS
        count += 1
        if os.path.isfile(file_path):
            found = True
        else:
            time.sleep(1)
    assert found, "After {} seconds, {} file not found".format(timeout, file_path)


def wait_for_themes(section):
    # ensure library is not refreshing
    while section.refreshing:
        time.sleep(1)

    # wait for themes to be uploaded
    timer = 0
    with_themes = 0
    total = len(section.all())
    while timer < 600 and with_themes < total:
        with_themes = 0
        try:
            for item in section.all():
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
@pytest.fixture(params=['movies', 'tv_shows'], scope="function")
def agent(request):
    # type: (any) -> Agent
    if request.param == 'movies':
        return ThemerrMovies()
    elif request.param == 'tv_shows':
        return ThemerrTvShows()
    else:
        return Themerr()


@pytest.fixture(scope='function')
def test_client():
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

    wait_for_file(file_path=plugin_log_file, timeout=300)

    yield plugin_log_file


@pytest.fixture(scope="session")
def sess():
    session = requests.Session()
    session.request = partial(session.request, timeout=120)
    return session


@pytest.fixture(scope="session")
def plex(request, sess):
    assert SERVER_BASEURL is not None, "Required SERVER_BASEURL not specified."

    return PlexServer(SERVER_BASEURL, SERVER_TOKEN, session=sess)


@pytest.fixture(params=MOVIE_SECTIONS, scope="session")
def movie_section_names(plex, request):
    library_section = request.param
    assert plex.library.section(library_section), "Required library section {} not found.".format(library_section)
    return library_section


@pytest.fixture(scope="session")
def movies(movie_section_names, plex):
    library_section = movie_section_names
    library_items = plex.library.section(library_section)
    wait_for_themes(section=library_items)
    yield library_items


@pytest.fixture(scope="session")
def collections(movie_section_names, movies, plex):
    library_section = movie_section_names
    try:
        return movies.collection("Test Collection")
    except NotFound:
        return plex.createCollection(
            title="Test Collection",
            section=library_section,
            items=movies.all()
        )


@pytest.fixture(params=TV_SHOW_SECTIONS, scope="session")
def tv_show_section_names(plex, request):
    library_section = request.param
    assert plex.library.section(library_section), "Required library section {} not found.".format(library_section)
    return library_section


@pytest.fixture(scope="session")
def tv_shows(tv_show_section_names, plex):
    library_section = tv_show_section_names
    library_items = plex.library.section(library_section)
    wait_for_themes(section=library_items)
    yield library_items


@pytest.fixture(params=MOVIE_SECTIONS + TV_SHOW_SECTIONS, scope="session")
def section_names(plex, request):
    library_section = request.param
    assert plex.library.section(library_section), "Required library section {} not found.".format(library_section)
    return library_section


@pytest.fixture(scope="session")
def section(section_names, plex):
    library_section = section_names
    library_items = plex.library.section(library_section)
    wait_for_themes(section=library_items)
    yield library_items


@pytest.fixture(scope='function')
def empty_themerr_db_cache():
    themerr_db_helper.database_cache = {}  # reset the cache
    themerr_db_helper.last_cache_update = 0
    return
