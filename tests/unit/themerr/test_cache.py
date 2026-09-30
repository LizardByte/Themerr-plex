"""Dashboard cache built from fake Plex sections and ThemerrDB lookups."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from themerr import cache


def test_cache_without_plex(monkeypatch):
    monkeypatch.setattr(cache, 'setup_plexapi', lambda: None)
    save = Mock()
    monkeypatch.setattr(cache.helpers, 'file_save', save)
    cache.cache_data()
    save.assert_not_called()


def test_cache_data(configured, item, tmp_path, monkeypatch):
    section = SimpleNamespace(
        agent='tv.plex.agents.movie', key=1, title='Movies', type='movie',
    )
    section.all = Mock(side_effect=lambda **kwargs: [item] if not kwargs else [])
    section.collections = Mock(return_value=[])
    unsupported = SimpleNamespace(agent='unsupported')
    plex = SimpleNamespace(library=SimpleNamespace(sections=lambda: [unsupported, section]))
    monkeypatch.setattr(cache, 'setup_plexapi', lambda: plex)
    monkeypatch.setattr(cache.themerr_db, 'update_cache', Mock())
    monkeypatch.setattr(cache.themerr_db, 'item_exists', lambda **_: False)
    monkeypatch.setattr(cache, 'get_database_info', lambda **_: ('movies', 'themoviedb', section.agent, '1'))
    monkeypatch.setattr(cache.general, 'get_theme_provider', lambda **_: None)
    monkeypatch.setattr(cache, 'database_cache_file', str(tmp_path / 'cache.json'))
    configured['Themerr']['BOOL_PLEX_COLLECTION_SUPPORT'] = False

    cache.cache_data()

    data = json.loads(Path(cache.database_cache_file).read_text(encoding='utf-8'))
    assert data['1']['media_count'] == 1
    assert data['1']['items'][0]['theme_status'] == 'missing'
    assert data['1']['items'][0]['issue_action'] == 'add'
    assert section.collections.call_count == 0


def test_cache_item_converts_imdb_id_and_marks_existing_theme(item, monkeypatch):
    item.theme = 'existing theme'
    monkeypatch.setattr(cache, 'get_database_info', lambda **_: (
        'movies', 'imdb', 'com.plexapp.agents.imdb', 'tt42',
    ))
    monkeypatch.setattr(cache.tmdb, 'get_tmdb_id_from_external_id', lambda **_: 99)
    monkeypatch.setattr(cache.themerr_db, 'item_exists', lambda **_: True)
    monkeypatch.setattr(cache.general, 'get_theme_provider', lambda **_: 'plex')

    data = cache._cache_item(item)

    assert data['database_id'] == 99
    assert data['issue_action'] == 'edit'
    assert data['theme_status'] == 'complete'
    assert data['theme_provider'] == 'plex'
    assert 'Example+%282020%29' in data['issue_url']
