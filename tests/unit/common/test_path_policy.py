"""Shared path checks must reject ambiguity and contain every filesystem lookup."""

# standard imports
import os

# lib imports
import pytest

# local imports
from common import path_policy


@pytest.mark.parametrize('filename', [
    '', '.', '..', '../private', '/private', 'nested//file', 'nested/../file', 'nested/./file',
    'C:/private', 'C:private', r'\\server\share', r'nested\file', '%2e%2e/private', '%252e%252e/private',
    'file:stream', 'NUL', 'CON.txt', 'file\x00', 'file\x09', 'file\x7f', 'file ', 'file.', 'a' * 4097,
])
def test_invalid_names_are_rejected_before_filesystem_access(filename, monkeypatch):
    def unexpected_lookup(*args, **kwargs):
        pytest.fail('Invalid path reached the filesystem')

    with monkeypatch.context() as patch:
        patch.setattr(path_policy.os.path, 'realpath', unexpected_lookup)
        with pytest.raises(ValueError):
            path_policy.resolve_file_path('/trusted/root', filename)


def test_nested_regular_files_are_resolved_but_directories_and_missing_files_are_rejected(tmp_path):
    nested = tmp_path / 'nested'
    nested.mkdir()
    file = nested / 'file.log'
    file.write_text('inside', encoding='utf-8')
    assert path_policy.resolve_file_path(str(tmp_path), 'nested/file.log') == str(file.resolve())
    with pytest.raises(FileNotFoundError):
        path_policy.resolve_file_path(str(tmp_path), 'nested')
    with pytest.raises(FileNotFoundError):
        path_policy.resolve_file_path(str(tmp_path), 'missing.log')


def test_canonical_paths_in_sibling_directories_are_rejected(tmp_path, monkeypatch):
    root = tmp_path / 'logs'
    root.mkdir()
    sibling = tmp_path / 'logs-private'
    sibling.mkdir()
    private = sibling / 'themerr.log'
    private.write_text('private', encoding='utf-8')
    realpath = os.path.realpath

    def redirected(path, **kwargs):
        if os.path.normpath(path) == str(root / 'themerr.log'):
            return str(private)
        return realpath(path, **kwargs)

    monkeypatch.setattr(path_policy.os.path, 'realpath', redirected)
    with pytest.raises(PermissionError):
        path_policy.resolve_file_path(str(root), 'themerr.log')
