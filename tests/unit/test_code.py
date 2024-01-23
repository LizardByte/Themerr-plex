# -*- coding: utf-8 -*-

# local imports
import Code
from Code import ValidatePrefs
from Code import default_prefs
from plexhints.agent_kit import Media
from plexhints.model_kit import Movie, MetadataModel
from plexhints.object_kit import MessageContainer, SearchResult
from plexhints.prefs_kit import Prefs

# setup items to test
test_items = dict(
    a=dict(
        primary_agent='dev.lizardbyte.retroarcher-plex',
        rating_key=1,
        title='007 - GoldenEye (USA)',
        year=1997,
        id='{igdb-1638}',
        category='games',
    ),
    b=dict(
        primary_agent='com.plexapp.agents.themoviedb',
        rating_key=2,
        title='GoldenEye',
        year=1995,
        id='710',
        category='movies',
    ),
    c=dict(
        primary_agent='com.plexapp.agents.imdb',
        rating_key=3,
        title='GoldenEye',
        year=1995,
        id='tt0113189',
        category='movies',
    ),
    d=dict(
        primary_agent='com.plexapp.agents.themoviedb',
        rating_key=4,
        title='The 100',
        year=2014,
        id='48866',
        category='tv_shows',
    ),
    e=dict(
        primary_agent='com.plexapp.agents.thetvdb',
        rating_key=4,
        title='The 100',
        year=2014,
        id='268592',
        category='tv_shows',
    ),
)


def test_copy_prefs():
    Code.copy_prefs()
    assert Code.last_prefs, "Prefs did not copy"

    for key in default_prefs:
        assert Code.last_prefs[key] == Prefs[key]


def test_validate_prefs():
    result_container = ValidatePrefs()
    assert isinstance(result_container, MessageContainer)
    assert result_container.header == "Success"
    assert "Provided preference values are ok" in result_container.message

    # invalidate prefs, cannot do this due to:
    # TypeError: '_PreferenceSet' object does not support item assignment
    # Code.Prefs['int_plexapi_plexapi_timeout'] = 'not an integer'
    # result_container = ValidatePrefs()
    # assert isinstance(result_container, MessageContainer)
    # assert result_container.header == "Error"
    # assert "must be an integer" in result_container.message


def test_validate_prefs_default_prefs():
    # add a default pref and make sure it is not in DefaultPrefs.json
    default_prefs['new_pref'] = 'new_value'
    result_container = ValidatePrefs()
    assert isinstance(result_container, MessageContainer)
    assert result_container.header == "Error"
    assert "missing from 'DefaultPrefs.json'" in result_container.message


def test_start():
    # todo
    pass


def test_main():
    # todo
    pass


def test_themerr_agent_search(agent):
    # if agent is for movies
    supported_categories = []
    if isinstance(agent, Code.ThemerrMovies):
        supported_categories.append('movies')
        supported_categories.append('games')
    elif isinstance(agent, Code.ThemerrTvShows):
        supported_categories.append('tv_shows')

    for key, item in test_items.items():
        if item['category'] not in supported_categories:
            continue

        if isinstance(agent, Code.ThemerrMovies):
            media = Media.Movie()
            media.primary_metadata = Movie()
        elif isinstance(agent, Code.ThemerrTvShows):
            media = Media.TV_Show()
            media.primary_metadata = MetadataModel()
        else:
            assert False, "Agent is not ThemerrMovies or ThemerrTvShows"

        media.primary_agent = item['primary_agent']
        media.primary_metadata.id = item['id']
        media.primary_metadata.title = item['title']
        media.primary_metadata.year = item['year']

        database = None
        item_id = item['id']
        if item['category'] == 'games':
            database = item['id'][1:-1].split('-')[0]
            item_id = item['id'][1:-1].split('-')[-1]
        elif item['category'] == 'movies' or item['category'] == 'tv_shows':
            database = item['primary_agent'].split('.')[-1]

        results = agent.search(results=SearchResult(), media=media, lang='en', manual=False)

        for result in results.__items__:
            # print(result.__dict__)
            assert result.name == item['title']
            assert result.year == item['year']
            assert result.id == "%s-%s-%s" % (item['category'], database, item_id)


def test_themerr_agent_update(agent):
    metadata = Movie()

    for key, item in test_items.items():
        media = Movie()

        database = None
        item_id = item['id']
        if item['category'] == 'games':
            database = item['id'][1:-1].split('-')[0]
            item_id = item['id'][1:-1].split('-')[-1]
        elif item['category'] == 'movies' or item['category'] == 'tv_shows':
            database = item['primary_agent'].split('.')[-1]

        media.id = item['rating_key']
        metadata.title = item['title']
        metadata.year = item['year']
        metadata.id = "%s-%s-%s" % (item['category'], database, item_id)

        # this won't actually upload a theme since we're not working with a real Plex Server
        metadata = agent.update(metadata=metadata, media=media, lang='en', force=True)

        assert isinstance(metadata, Movie)
