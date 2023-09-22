# -*- coding: utf-8 -*-
# local imports
from Code import lizardbyte_db_helper


def test_get_igdb_id_from_collection():
    tests = [
        {
            'search_query': 'James Bond',
            'collection_type': 'game_collections',
            'expected_type': 'game_collections',
            'expected_id': 326,
        },
        {
            'search_query': 'James Bond',
            'collection_type': 'game_franchises',
            'expected_type': 'game_franchises',
            'expected_id': 37,
        },
        {
            'search_query': 'James Bond',
            'collection_type': None,
            'expected_type': 'game_collections',
            'expected_id': 326,
        },
    ]

    for test in tests:
        igdb_id = lizardbyte_db_helper.get_igdb_id_from_collection(
            search_query=test['search_query'],
            collection_type=test['collection_type']
        )
        assert igdb_id == (test['expected_id'], test['expected_type'])


def test_get_igdb_id_from_collection_invalid():
    test = lizardbyte_db_helper.get_igdb_id_from_collection(search_query='Not a real collection')
    assert test is None

    invalid_collection_type = lizardbyte_db_helper.get_igdb_id_from_collection(
        search_query='James Bond',
        collection_type='invalid',
    )
    assert invalid_collection_type is None
