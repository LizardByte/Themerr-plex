# -*- coding: utf-8 -*-
# lib imports
import plexhints

# local imports
from Code import tmdb_helper


def test_get_tmdb_id_from_imdb_id():
    print(plexhints.CONTENTS)
    print(plexhints.ELEVATED_POLICY)
    tests = [
        'tt1254207'
    ]

    for test in tests:
        tmdb_id = tmdb_helper.get_tmdb_id_from_imdb_id(imdb_id=test)
        assert tmdb_id, "No tmdb_id found for {}".format(test)
        assert isinstance(tmdb_id, int), "tmdb_id is not an int: {}".format(tmdb_id)


def test_get_tmdb_id_from_imdb_id_invalid():
    test = tmdb_helper.get_tmdb_id_from_imdb_id(imdb_id='invalid')
    assert test is None, "tmdb_id found for invalid imdb_id: {}".format(test)


def test_get_tmdb_id_from_collection():
    tests = [
        'James Bond',
        'James Bond Collection',
    ]

    for test in tests:
        tmdb_id = tmdb_helper.get_tmdb_id_from_collection(search_query=test)
        assert tmdb_id, "No tmdb_id found for {}".format(test)
        assert isinstance(tmdb_id, int), "tmdb_id is not an int: {}".format(tmdb_id)


def test_get_tmdb_id_from_collection_invalid():
    test = tmdb_helper.get_tmdb_id_from_collection(search_query='Not a real collection')
    assert test is None, "tmdb_id found for invalid collection: {}".format(test)
