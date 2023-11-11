# -*- coding: utf-8 -*-
# standard imports
import os
import shutil

# lib imports
import pytest

# local imports
from Code import plex_api_helper
from Code import themerr_db_helper

def test_update_cache():
    themerr_db_helper.update_cache()

def test_item_exists():
    global plex
    if not plex:
        plex = plex_api_helper.setup_plexapi()

    movies = plex.library.section("Movies") 

    themerr_db_helper.update_cache()

    media_items = movies.all()
    collections = movies.collections()

    all_items = media_items + collections

    for item in all_items:
        database_info = plex_api_helper.get_database_info(item=item)

        database_type = database_info[0]
        database = database_info[1]
        database_id = database_info[3]

        assert themerr_db_helper.item_exists(database_type=database_type, database=database, id=database_id) is True
