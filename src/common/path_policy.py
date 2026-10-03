"""Shared containment policy for reading files beneath a trusted server directory."""

# standard imports
import ntpath
import os

# lib imports
from werkzeug.security import safe_join


_INVALID_RELATIVE_PATH = 'Invalid relative file name'


def validate_relative_path(filename: str) -> None:
    """Validate an unambiguous relative file name.

    Apply the same URL and Windows path restrictions on every platform. Call before
    normalization so dot segments and encoded separators cannot disappear.

    Parameters
    ----------
    filename : str
        Relative name, using forward slashes for nested files.

    Raises
    ------
    ValueError
        The name is empty, too long, absolute, encoded, reserved, or contains dot segments.
    """
    if not filename or len(filename) > 4096 or any(
            character in '\\:%' or ord(character) < 32 or ord(character) == 127 for character in filename):
        raise ValueError(_INVALID_RELATIVE_PATH)
    if any(part in ('', '.', '..') or ntpath.isreserved(part) for part in filename.split('/')):
        raise ValueError(_INVALID_RELATIVE_PATH)


def resolve_file_path(directory: str, filename: str) -> str:
    """Resolve an existing file while enforcing canonical directory containment.

    Use a server-owned directory and prefer fixed file names selected from an allowlist.
    Resolve symlinks and Windows junctions before checking containment; a similarly
    named sibling directory is outside the root.

    Parameters
    ----------
    directory : str
        Trusted root directory, supplied by application code or configuration.
    filename : str
        Relative file name validated before joining it to the root.

    Returns
    -------
    str
        Canonical absolute path of a regular file inside the root.

    Raises
    ------
    ValueError
        The relative file name is invalid.
    OSError
        The file is missing, unreadable, not a regular file, or resolves outside the root.
    """
    validate_relative_path(filename)
    root = os.path.realpath(directory, strict=True)
    joined = safe_join(root, filename)
    if joined is None:
        raise ValueError(_INVALID_RELATIVE_PATH)
    path = os.path.realpath(joined, strict=True)
    if os.path.commonpath((root, path)) != root:
        raise PermissionError('File is outside the permitted directory')
    if not os.path.isfile(path):
        raise FileNotFoundError('Not a regular file')
    return path
