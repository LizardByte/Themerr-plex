"""ThemerrDB indexing and lookup without hosted data."""

from themerr import themerr_db


def test_update_cache_and_lookup(monkeypatch):
    calls = []

    def get_json(**kwargs):
        url = kwargs['url']
        calls.append(url)
        if url.endswith('pages.json'):
            return {'pages': 2}
        if '/movie_collections/' in url:
            return [{'id': 645, 'title': 'James Bond Collection'}]
        if '/tv_shows/' in url:
            return [{'id': 456, 'title': 'Example Show'}]
        return [{'id': 123, 'imdb_id': 'tt123', 'title': 'Example Movie'}]

    monkeypatch.setattr(themerr_db.helpers, 'json_get', get_json)
    monkeypatch.setattr(themerr_db.time, 'time', lambda: 10000)
    monkeypatch.setattr(themerr_db, 'database_cache', {})
    monkeypatch.setattr(themerr_db, 'lookup_cache', {})
    monkeypatch.setattr(themerr_db, 'last_cache_update', 0)

    themerr_db.update_cache()
    assert len(calls) == 9
    assert themerr_db.item_exists('movies', 'themoviedb', 123)
    assert themerr_db.item_exists('movies', 'imdb', 'tt123')
    assert themerr_db.find_movie_id_by_imdb('tt123') == 123
    assert themerr_db.find_id_by_title('movie_collections', 'James Bond') == 645
    assert themerr_db.find_id_by_title('movie_collections', 'james-bond collection') == 645
    assert themerr_db.find_id_by_title('tv_shows', 'Example Show') == 456
    assert themerr_db.find_id_by_title('tv_shows', 'Missing Show') is None
    assert not themerr_db.item_exists('movies', 'imdb', 'missing')
    assert not themerr_db.item_exists('invalid', 'imdb', 'tt123')
    themerr_db.update_cache()
    assert len(calls) == 9


def test_failed_database_fetch(monkeypatch):
    monkeypatch.setattr(themerr_db, 'database_cache', {})
    monkeypatch.setattr(themerr_db, 'lookup_cache', {})
    monkeypatch.setattr(themerr_db, 'last_cache_update', 0)
    monkeypatch.setattr(themerr_db.time, 'time', lambda: 10000)

    def fail(**_):
        raise RuntimeError('offline')

    monkeypatch.setattr(themerr_db.helpers, 'json_get', fail)
    themerr_db.update_cache()
    assert themerr_db.database_cache == {
        'movies': {}, 'movie_collections': {}, 'tv_shows': {},
    }
    assert not themerr_db.item_exists('movies', 'themoviedb', 1)
    assert themerr_db.find_id_by_title('movie_collections', 'Missing') is None
