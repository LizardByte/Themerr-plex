"""CI stamps release metadata before packaging and supports native macOS notifications."""

import importlib.util
from pathlib import Path
import runpy
import sys
from unittest.mock import Mock

import pytest
import PyInstaller.__main__

from common import definitions, version


@pytest.mark.parametrize('platform', ['win32', 'linux', 'darwin'])
def test_build_stamps_ci_version_before_packaging(monkeypatch, tmp_path, platform):
    source = Path(__file__).resolve().parents[2] / 'scripts' / 'build.py'
    spec = importlib.util.spec_from_file_location('notification_build', source)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    monkeypatch.setattr(builder, 'build_connector', Mock())
    module = tmp_path / 'src' / 'common' / 'version.py'
    module.parent.mkdir(parents=True)
    monkeypatch.setattr(builder, '__file__', str(tmp_path / 'scripts' / 'build.py'))
    monkeypatch.setattr(builder.sys, 'platform', platform)
    monkeypatch.setattr(builder.shutil, 'which', lambda _: '/tools/deno')
    monkeypatch.setenv('THEMERR_VERSION', '2026.1003.120000')
    monkeypatch.delenv('APPLE_CODESIGN_IDENTITY', raising=False)

    def bundle(arguments):
        assert runpy.run_path(str(module))['VERSION'] == '2026.1003.120000'
        assert not any('version.txt' in value for value in arguments)
        assert any(value.startswith('--add-data=jellyfin-connector') for value in arguments)
        assert not any(value.startswith('--codesign-identity=') for value in arguments)
        if platform == 'darwin':
            assert '--onedir' in arguments
            assert '--windowed' in arguments
            assert '--onefile' not in arguments
        else:
            assert '--onefile' in arguments

    monkeypatch.setattr(PyInstaller.__main__, 'run', bundle)
    builder.build()
    # A later local build without CI metadata keeps the stamped version.
    monkeypatch.delenv('THEMERR_VERSION')
    builder.build()


def test_mac_bundle_keeps_user_configuration_outside_signed_resources(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    monkeypatch.setattr(sys, 'executable', '/Applications/themerr_plex.app/Contents/MacOS/themerr_plex')
    monkeypatch.delenv('THEMERR_DOCKER', raising=False)
    data = runpy.run_path(definitions.__file__)
    assert Path(data['Paths'].DATA_DIR).as_posix().endswith('Library/Application Support/Themerr-plex')
    assert '.app' not in data['Paths'].CONFIG_DIR


def test_version_option_exits_before_initialization(monkeypatch, capsys):
    import common
    import themerr_plex
    monkeypatch.setattr(sys, 'argv', ['themerr_plex.py', '--version'])
    monkeypatch.setattr(version, 'VERSION', '2026.1003.120000')
    initialize = Mock()
    monkeypatch.setattr(common, 'initialize', initialize)
    with pytest.raises(SystemExit) as result:
        themerr_plex.main()
    assert result.value.code is None
    assert capsys.readouterr().out.strip() == 'Themerr-plex 2026.1003.120000'
    initialize.assert_not_called()
