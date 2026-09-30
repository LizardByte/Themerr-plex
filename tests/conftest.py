"""Local fixtures; tests do not require a Plex server or network access."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def configured(tmp_path, monkeypatch):
    import common
    from common import config, definitions

    old_config, old_common = config.CONFIG, common.CONFIG
    monkeypatch.setattr(definitions.Paths, 'CONFIG_DIR', str(tmp_path))
    cfg = config.create_config(str(tmp_path / 'config.ini'))
    common.CONFIG = cfg
    try:
        yield cfg
    finally:
        config.CONFIG, common.CONFIG = old_config, old_common


@pytest.fixture
def item():
    value = SimpleNamespace(
        title='Example', type='movie', ratingKey=42,
        guid='plex://movie/example', guids=[],
        theme=None, year=2020, librarySectionID=1,
    )
    value.themes = Mock(return_value=[])
    value.isLocked = Mock(return_value=False)
    value.edit = Mock()
    value.reload = Mock()
    value.uploadTheme = Mock()
    value.uploadArt = Mock()
    value.uploadPoster = Mock()
    return value
