# -*- coding: utf-8 -*-

# standard imports
import json
import os

# local imports
from Code import webapp


def test_cache_data():
    webapp.cache_data()
    assert os.path.isfile(webapp.database_cache_file), "Database cache file not found"

    with open(webapp.database_cache_file, 'r') as f:
        data = json.load(f)

    assert data, "Database cache file is empty"
