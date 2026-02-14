"""
tests/conftest.py

Fixtures for pytest.
"""
# standard imports
from functools import partial
import os
import sys
import time

# lib imports
import plexapi
from plexapi.exceptions import NotFound
from plexapi.server import PlexServer
import pytest
import requests

# add Contents directory to the system path
pytest.root_dir = root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pytest.src_dir = src_dir = os.path.join(root_dir, 'src')

if os.path.isdir(src_dir):  # avoid flake8 E402 warning
    sys.path.insert(0, src_dir)

    # local imports
    import common
    from common import config
    from common import definitions
    from common import webapp
    from themerr import themerr_db
else:
    raise Exception('src directory not found')

# plex server setup
SERVER_BASEURL = plexapi.CONFIG.get("auth.server_baseurl")
SERVER_TOKEN = plexapi.CONFIG.get("auth.server_token")

# constants
MOVIE_SECTIONS = ["Movies"]
TV_SHOW_SECTIONS = ["TV Shows"]


def wait_for_themes(section):
    # ensure library is not refreshing
    while section.refreshing:
        time.sleep(1)

    # wait for themes to be uploaded
    timer = 0
    with_themes = 0
    total = len(section.all())
    while timer < 180 and with_themes < total:
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


@pytest.fixture(scope='function')
def test_config_file():
    """Set a test config file path"""
    test_config_file = os.path.join(definitions.Paths.CONFIG_DIR, 'test_config.ini')  # use a dummy ini file

    yield test_config_file


@pytest.fixture(scope='function')
def test_config_object(test_config_file):
    """Create a test config object"""
    test_config_object = config.create_config(config_file=test_config_file)

    config.CONFIG = test_config_object

    yield test_config_object


@pytest.fixture(scope='function')
def test_common_init(test_config_file):
    test_common_init = common.initialize(config_file=test_config_file)

    yield test_common_init

    common._INITIALIZED = False
    common.SIGNAL = 'shutdown'


@pytest.fixture(scope='function')
def test_client(test_common_init):
    """Create a test client for testing webapp endpoints"""
    app = webapp.app
    app.testing = True

    client = app.test_client()

    # Create a test client using the Flask application configured for testing
    with client as test_client:
        # Establish an application context
        with app.app_context():
            yield test_client  # this is where the testing happens!


# plex server fixtures
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
    themerr_db.database_cache = {}  # reset the cache
    themerr_db.last_cache_update = 0
    return
