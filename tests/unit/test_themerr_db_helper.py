# -*- coding: utf-8 -*-

# local imports
from Code import plex_api_helper
from Code import themerr_db_helper


def test_update_cache(empty_themerr_db_cache):
    themerr_db_helper.update_cache()
    assert themerr_db_helper.last_cache_update > 0, 'Cache update did not complete'

    assert "movies" in themerr_db_helper.database_cache, 'Cache does not contain movies'
    assert "movie_collections" in themerr_db_helper.database_cache, 'Cache does not contain movie_collections'
    assert "games" in themerr_db_helper.database_cache, 'Cache does not contain games'
    assert "game_collections" in themerr_db_helper.database_cache, 'Cache does not contain game_collections'
    assert "game_franchises" in themerr_db_helper.database_cache, 'Cache does not contain game_franchises'
    assert "tv_shows" in themerr_db_helper.database_cache, 'Cache does not contain tv_shows'


def test_item_exists(empty_themerr_db_cache, section):
    for item in section.all():
        database_info = plex_api_helper.get_database_info(item=item)

        database_type = database_info[0]
        database = database_info[1]
        database_id = database_info[3]

        assert themerr_db_helper.item_exists(database_type=database_type, database=database, id=database_id), \
            '{} {} {} does not exist in ThemerrDB'.format(database, database_type, database_id)


def test_item_exists_with_invalid_database():
    # movie is not valid... the correct type is movies
    assert not themerr_db_helper.item_exists(database_type='movie', database='invalid', id='invalid'), \
        'Invalid database should not exist in ThemerrDB'
