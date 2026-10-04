"""Local fixtures; tests do not require a Plex server or network access."""

# standard imports
from types import SimpleNamespace
from unittest.mock import Mock

# lib imports
import pytest


@pytest.fixture
def configured(tmp_path, monkeypatch):
    import common
    from common import config, definitions, notifications
    from plex import token_store
    from themerr import storage

    old_config, old_common = config.CONFIG, common.CONFIG
    passwords = {}
    monkeypatch.delenv(token_store.KEY_FILE_ENV, raising=False)
    monkeypatch.delenv('THEMERR_DOCKER', raising=False)
    monkeypatch.setattr(token_store.keyring, 'get_password', lambda service, client: passwords.get((service, client)))
    monkeypatch.setattr(token_store.keyring, 'set_password',
                        lambda service, client, token: passwords.__setitem__((service, client), token))
    monkeypatch.setattr(token_store.keyring, 'delete_password',
                        lambda service, client: passwords.pop((service, client), None))
    monkeypatch.setattr(definitions.Paths, 'CONFIG_DIR', str(tmp_path))
    monkeypatch.setattr(notifications, '_desktop_available', lambda: False)
    cfg = config.create_config(str(tmp_path / 'config.ini'))
    common.CONFIG = cfg
    try:
        yield cfg
    finally:
        storage.close()
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
