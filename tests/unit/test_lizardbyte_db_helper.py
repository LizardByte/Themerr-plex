# -*- coding: utf-8 -*-

# lib imports
import pytest

# local imports
from Code import lizardbyte_db_helper


@pytest.mark.parametrize('search_query, collection_type, expected_type, expected_id', [
    ('James Bond', 'game_collections', 'game_collections', 326),
    ('James Bond', 'game_franchises', 'game_franchises', 37),
    ('James Bond', None, 'game_collections', 326),
])
def test_get_igdb_id_from_collection(search_query, collection_type, expected_type, expected_id):
    igdb_id = lizardbyte_db_helper.get_igdb_id_from_collection(
        search_query=search_query,
        collection_type=collection_type
    )
    assert igdb_id == (expected_id, expected_type)


def test_get_igdb_id_from_collection_invalid():
    test = lizardbyte_db_helper.get_igdb_id_from_collection(search_query='Not a real collection')
    assert test is None

    invalid_collection_type = lizardbyte_db_helper.get_igdb_id_from_collection(
        search_query='James Bond',
        collection_type='invalid',
    )
    assert invalid_collection_type is None
