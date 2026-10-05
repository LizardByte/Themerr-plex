"""Local fixtures; tests do not require a Plex server or network access."""

# standard imports
from types import SimpleNamespace
from unittest.mock import Mock
import hashlib
import json

# lib imports
import pytest


@pytest.fixture
def connector_bundle(tmp_path, monkeypatch):
    from jellyfin import connector
    from common.version import VERSION
    directory = tmp_path / 'connector'
    directory.mkdir()
    (directory / 'thumb.png').write_bytes(b'\x89PNG\r\n\x1a\nthumbnail')
    artifacts = {}
    for index, (profile, filename) in enumerate(connector.ARCHIVES.items()):
        content = ('connector-' + profile).encode()
        (directory / filename).write_bytes(content)
        artifacts[profile] = {'version': f'2026.1004.1234.{index}', 'targetAbi': profile + '.0',
                              'checksum': hashlib.md5(content, usedforsecurity=False).hexdigest()}
    data = {'build': 'a' * 64, 'protocol': 1, 'themerrVersion': VERSION, 'artifacts': artifacts}
    (directory / 'bundle.json').write_text(json.dumps(data), encoding='utf-8')
    monkeypatch.setattr(connector, 'directory', lambda: directory)
    return data


@pytest.fixture
def configured(tmp_path, monkeypatch):
    import common
    from common import config, definitions, notifications
    from jellyfin import maintenance
    from plex import token_store
    from themerr import storage

    old_config, old_common = config.CONFIG, common.CONFIG
    passwords = {}
    monkeypatch.delenv(token_store.KEY_FILE_ENV, raising=False)
    monkeypatch.delenv('THEMERR_PLEX_TOKEN_KEY_FILE', raising=False)
    monkeypatch.setattr(maintenance, 'start', lambda: None)
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
