"""CI stamps release metadata before packaging and supports native macOS notifications."""

# standard imports
import importlib.util
from pathlib import Path
import runpy
import sys
from unittest.mock import Mock

# lib imports
import pytest
import PyInstaller.__main__

# local imports
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
    monkeypatch.delenv('THEMERR_DOCKER', raising=False)
    monkeypatch.delenv('APPLE_CODESIGN_IDENTITY', raising=False)

    def bundle(arguments):
        assert runpy.run_path(str(module))['VERSION'] == '2026.1003.120000'
        assert arguments[0] == './src/main.py'
        assert '--name=themerr' in arguments
        assert not any('version.txt' in value for value in arguments)
        assert any(value.startswith('--add-data=jellyfin-connector') for value in arguments)
        assert any(value.startswith('--add-binary=/tools/deno') for value in arguments)
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


@pytest.mark.parametrize('platform', (
    'win32',
    'linux',
    'darwin',
))
def test_native_build_bundles_local_deno_when_missing_from_path(monkeypatch, tmp_path, platform):
    source = Path(__file__).resolve().parents[2] / 'scripts' / 'build.py'
    spec = importlib.util.spec_from_file_location('local_deno_build', source)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    monkeypatch.setattr(builder, 'build_connector', Mock())
    monkeypatch.setattr(builder, '__file__', str(tmp_path / 'scripts' / 'build.py'))
    monkeypatch.setattr(builder.sys, 'platform', platform)
    monkeypatch.setattr(builder.shutil, 'which', lambda _: None)
    monkeypatch.delenv('THEMERR_DOCKER', raising=False)
    monkeypatch.delenv('THEMERR_VERSION', raising=False)
    deno = tmp_path / '.build-tools' / ('deno.exe' if platform == 'win32' else 'deno')
    deno.parent.mkdir()
    deno.touch()
    bundle = Mock()
    monkeypatch.setattr(PyInstaller.__main__, 'run', bundle)

    builder.build()

    assert f'--add-binary={deno}{builder.os.pathsep}.' in bundle.call_args.args[0]

    deno.unlink()
    bundle.reset_mock()
    with pytest.raises(SystemExit, match='Deno is required to bundle yt-dlp YouTube support.'):
        builder.build()
    bundle.assert_not_called()


def test_docker_build_uses_external_deno_without_splash(monkeypatch):
    source = Path(__file__).resolve().parents[2] / 'scripts' / 'build.py'
    spec = importlib.util.spec_from_file_location('docker_build', source)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    monkeypatch.setattr(builder, 'build_connector', Mock())
    monkeypatch.setattr(builder.sys, 'platform', 'linux')
    monkeypatch.setattr(builder.shutil, 'which', lambda _: None)
    monkeypatch.setenv('THEMERR_DOCKER', 'True')
    monkeypatch.delenv('THEMERR_VERSION', raising=False)
    bundle = Mock()
    monkeypatch.setattr(PyInstaller.__main__, 'run', bundle)

    builder.build()

    arguments = bundle.call_args.args[0]
    assert '--onefile' in arguments
    assert any(value.startswith('--add-data=jellyfin-connector') for value in arguments)
    assert not any(value.startswith('--add-binary=') for value in arguments)
    assert not any(value.startswith('--splash=') for value in arguments)


@pytest.mark.parametrize('existing_directory', (
    None,
    definitions.Names.legacy_name,
    definitions.Names.name,
))
def test_mac_bundle_keeps_user_configuration_outside_signed_resources(monkeypatch, tmp_path, existing_directory):
    directory = tmp_path / 'Library' / 'Application Support'
    if existing_directory:
        (directory / existing_directory).mkdir(parents=True)
    monkeypatch.setattr(definitions.os.path, 'expanduser', lambda path: str(directory / definitions.Names.name))
    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    monkeypatch.setattr(sys, 'executable', '/Applications/themerr.app/Contents/MacOS/themerr')
    monkeypatch.delenv('THEMERR_DOCKER', raising=False)
    data = runpy.run_path(definitions.__file__)
    assert Path(data['Paths'].DATA_DIR) == directory / (existing_directory or definitions.Names.name)
    assert '.app' not in data['Paths'].CONFIG_DIR


def test_frozen_docker_disables_splash(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    monkeypatch.setenv('THEMERR_DOCKER', 'True')

    modes = runpy.run_path(definitions.__file__)['Modes']

    assert modes.FROZEN
    assert modes.DOCKER
    assert not modes.SPLASH


def test_version_option_exits_before_initialization(monkeypatch, capsys):
    import common
    import main
    monkeypatch.setattr(sys, 'argv', ['main.py', '--version'])
    monkeypatch.setattr(version, 'VERSION', '2026.1003.120000')
    initialize = Mock()
    monkeypatch.setattr(common, 'initialize', initialize)
    with pytest.raises(SystemExit) as result:
        main.main()
    assert result.value.code is None
    assert capsys.readouterr().out.strip() == 'Themerr 2026.1003.120000'
    initialize.assert_not_called()
