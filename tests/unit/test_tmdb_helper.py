# -*- coding: utf-8 -*-

# lib imports
import plexhints
import pytest

# local imports
from Code import tmdb_helper


@pytest.mark.parametrize('tmdb_test_id', [
    'tt1254207',
])
def test_get_tmdb_id_from_imdb_id(tmdb_test_id):
    print(plexhints.CONTENTS)
    print(plexhints.ELEVATED_POLICY)

    tmdb_id = tmdb_helper.get_tmdb_id_from_imdb_id(imdb_id=tmdb_test_id)
    assert tmdb_id, "No tmdb_id found for {}".format(tmdb_test_id)
    assert isinstance(tmdb_id, int), "tmdb_id is not an int: {}".format(tmdb_id)


def test_get_tmdb_id_from_imdb_id_invalid():
    test = tmdb_helper.get_tmdb_id_from_imdb_id(imdb_id='invalid')
    assert test is None, "tmdb_id found for invalid imdb_id: {}".format(test)


@pytest.mark.parametrize('tmdb_test_collection', [
    'James Bond',
    'James Bond Collection',
])
def test_get_tmdb_id_from_collection(tmdb_test_collection):
    tmdb_id = tmdb_helper.get_tmdb_id_from_collection(search_query=tmdb_test_collection)
    assert tmdb_id, "No tmdb_id found for {}".format(tmdb_test_collection)
    assert isinstance(tmdb_id, int), "tmdb_id is not an int: {}".format(tmdb_id)


def test_get_tmdb_id_from_collection_invalid():
    test = tmdb_helper.get_tmdb_id_from_collection(search_query='Not a real collection')
    assert test is None, "tmdb_id found for invalid collection: {}".format(test)
