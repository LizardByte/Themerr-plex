"""
scripts/build.py

Creates spec and builds binaries for Themerr-plex.
"""
# standard imports
import os
import shutil
import sys

# lib imports
import PyInstaller.__main__


def build():
    """Sets arguments for pyinstaller, creates spec, and builds binaries."""
    deno = shutil.which('deno')
    if deno is None:
        executable = 'deno.exe' if sys.platform == 'win32' else 'deno'
        local_deno = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.build-tools', executable)
        deno = local_deno if os.path.isfile(local_deno) else None
    if deno is None:
        raise SystemExit('Deno is required to bundle yt-dlp YouTube support.')

    pyinstaller_args = [
        './src/themerr_plex.py',
        '--onefile',
        '--noconfirm',
        '--paths=./src',
        '--collect-all=av',
        f'--add-data=_site{os.pathsep}_site',
        f'--add-data=web{os.pathsep}web',
        f'--add-data=locale{os.pathsep}locale',
        f'--add-data=src/themerr/migrations{os.pathsep}themerr/migrations',
        f'--add-binary={deno}{os.pathsep}.',
        '--icon=./web/images/favicon.ico'
    ]

    if sys.platform.lower() == 'win32':  # windows
        pyinstaller_args.append('--console')
        pyinstaller_args.append('--splash=./web/images/icon-default.png')

    elif sys.platform.lower() == 'darwin':  # macOS
        pyinstaller_args.append('--console')
        pyinstaller_args.append('--osx-bundle-identifier=dev.lizardbyte.app.themerr-plex')

    elif sys.platform.lower() == 'linux':  # linux
        pyinstaller_args.append('--splash=./web/images/icon-default.png')

    PyInstaller.__main__.run(pyinstaller_args)


if __name__ == '__main__':
    build()
