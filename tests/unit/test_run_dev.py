"""Local development launcher without starting the application."""

# standard imports
import os
import sys
from types import ModuleType
from unittest.mock import Mock

# lib imports
import pytest

# local imports
from scripts import run_dev


def test_assets_rebuild_only_when_sources_change(tmp_path, monkeypatch):
    monkeypatch.setattr(run_dev, 'ROOT', tmp_path)
    (tmp_path / 'web' / 'assets').mkdir(parents=True)
    (tmp_path / 'web' / 'js').mkdir()
    (tmp_path / 'web' / 'css').mkdir()
    (tmp_path / 'scripts').mkdir()
    for source in ('scripts/build-assets.mjs', 'package.json', 'package-lock.json'):
        (tmp_path / source).touch()
    outputs = [tmp_path / 'web' / 'assets' / name for name in ('app.js', 'app.css', 'api_docs.js', 'api_docs.css')]
    for output in outputs:
        output.touch()
    assert not run_dev._assets_need_build()
    source = tmp_path / 'web' / 'js' / 'app.js'
    source.write_text('changed', encoding='utf-8')
    newer = max(output.stat().st_mtime_ns for output in outputs) + 1_000_000_000
    os.utime(source, ns=(newer, newer))
    assert run_dev._assets_need_build()


def test_ensure_assets_uses_locked_install(tmp_path, monkeypatch):
    monkeypatch.setattr(run_dev, 'ROOT', tmp_path)
    (tmp_path / 'package-lock.json').touch()
    monkeypatch.setattr(run_dev.shutil, 'which', lambda _: 'npm')
    monkeypatch.setattr(run_dev, '_assets_need_build', lambda: True)
    run = Mock()
    monkeypatch.setattr(run_dev.subprocess, 'run', run)

    run_dev._ensure_assets()

    assert [call.args[0] for call in run.call_args_list] == [
        ['npm', 'ci', '--ignore-scripts'],
        ['npm', 'run', 'build'],
    ]
    assert all(call.kwargs == {'cwd': tmp_path, 'check': True} for call in run.call_args_list)


@pytest.mark.parametrize(
    'relative_path',
    [
        'docs/source/index.rst',
        'connectors/jellyfin/ThemeFiles.cs',
        'connectors/jellyfin/Themerr.Connector.csproj',
        'docs/dockle_sphinx.py',
        'docs/connector_docs.py',
        'docs/environment.yml',
        'dockle.toml',
    ],
)
def test_docs_rebuild_when_source_changes(tmp_path, monkeypatch, relative_path):
    monkeypatch.setattr(run_dev, 'ROOT', tmp_path)
    index = tmp_path / '_site' / 'index.html'
    index.parent.mkdir()
    index.touch()
    source = tmp_path / relative_path
    source.parent.mkdir(parents=True, exist_ok=True)
    source.touch()
    newer = index.stat().st_mtime_ns + 1_000_000_000
    os.utime(source, ns=(newer, newer))

    assert run_dev._docs_need_build()


def test_main_runs_source_in_current_process(tmp_path, monkeypatch):
    monkeypatch.setattr(run_dev, 'ROOT', tmp_path)
    monkeypatch.setattr(run_dev.os, 'chdir', lambda _: None)
    monkeypatch.setattr(run_dev, '_ensure_assets', Mock())
    monkeypatch.setattr(run_dev, '_ensure_docs', Mock())
    monkeypatch.setattr(run_dev, '_has_js_runtime', lambda: True)
    app = ModuleType('themerr_plex')
    app.main = Mock()
    monkeypatch.setitem(sys.modules, 'themerr_plex', app)
    monkeypatch.syspath_prepend(str(tmp_path))
    run_dev.main()

    app.main.assert_called_once_with()
    run_dev._ensure_assets.assert_called_once_with()
    run_dev._ensure_docs.assert_called_once_with()
