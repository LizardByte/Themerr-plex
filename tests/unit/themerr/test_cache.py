# standard imports
import json
import os

# local imports
from themerr import cache


def test_cache_data():
    cache.cache_data()
    assert os.path.isfile(cache.database_cache_file), "Database cache file not found"

    with open(cache.database_cache_file, 'r') as f:
        data = json.load(f)

    assert data, "Database cache file is empty"
