# lib imports
import pytest

# local imports
from themerr import tmdb


@pytest.mark.parametrize('tmdb_test_id, database, item_type', [
    ('tt1254207', 'imdb', 'movie'),
    ('268592', 'tvdb', 'tv'),
])
def test_get_tmdb_id_from_external_id(tmdb_test_id, database, item_type):
    tmdb_id = tmdb.get_tmdb_id_from_external_id(external_id=tmdb_test_id, database=database, item_type=item_type)
    assert tmdb_id, "No tmdb_id found for {}".format(tmdb_test_id)
    assert isinstance(tmdb_id, int), "tmdb_id is not an int: {}".format(tmdb_id)


@pytest.mark.parametrize('tmdb_test_id, database, item_type', [
    ('invalid', 'imdb', 'movie'),
    ('tt1254207', 'invalid', 'movie'),
    ('invalid', 'imdb', 'game'),
])
def test_get_tmdb_id_from_external_id_invalid(tmdb_test_id, database, item_type):
    test = tmdb.get_tmdb_id_from_external_id(external_id=tmdb_test_id, database=database, item_type=item_type)
    assert test is None, "tmdb_id found for invalid imdb_id: {}".format(test)


@pytest.mark.parametrize('tmdb_test_collection', [
    'James Bond',
    'James Bond Collection',
])
def test_get_tmdb_id_from_collection(tmdb_test_collection):
    tmdb_id = tmdb.get_tmdb_id_from_collection(search_query=tmdb_test_collection)
    assert tmdb_id, "No tmdb_id found for {}".format(tmdb_test_collection)
    assert isinstance(tmdb_id, int), "tmdb_id is not an int: {}".format(tmdb_id)


def test_get_tmdb_id_from_collection_invalid():
    test = tmdb.get_tmdb_id_from_collection(search_query='Not a real collection')
    assert test is None, "tmdb_id found for invalid collection: {}".format(test)
