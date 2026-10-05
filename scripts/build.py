"""
scripts/build.py

Creates spec and builds binaries for Themerr-plex.
"""
# standard imports
import os
from pathlib import Path
import shutil
import sys
import runpy

# lib imports
import PyInstaller.__main__


def build_connector():
    """Validate CI's shared artifacts or compile the connectors for a local build."""
    builder = runpy.run_path(str(Path(__file__).with_name('build_connector.py')))
    if os.environ.get('THEMERR_PREBUILT_CONNECTOR') == '1':
        builder['check_bundle']()
    else:
        builder['build']()


def build():
    """Sets arguments for pyinstaller, creates spec, and builds binaries."""
    release_version = os.environ.get('THEMERR_VERSION')
    if release_version:
        version_file = Path(__file__).resolve().parents[1] / 'src' / 'common' / 'version.py'
        version_file.write_text(
            f'"""Release identity stamped by the release setup action."""\n\nVERSION = {release_version!r}\n',
            encoding='utf-8',
        )
    build_connector()
    deno = shutil.which('deno')
    if deno is None:
        executable = 'deno.exe' if sys.platform == 'win32' else 'deno'
        local_deno = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.build-tools', executable)
        deno = local_deno if os.path.isfile(local_deno) else None
    if deno is None:
        raise SystemExit('Deno is required to bundle yt-dlp YouTube support.')

    pyinstaller_args = [
        './src/themerr_plex.py',
        '--onedir' if sys.platform == 'darwin' else '--onefile',
        '--noconfirm',
        '--paths=./src',
        '--collect-all=av',
        '--hidden-import=uvicorn.loops.asyncio',
        '--hidden-import=uvicorn.protocols.http.h11_impl',
        '--hidden-import=uvicorn.lifespan.off',
        f'--add-data=_site{os.pathsep}_site',
        f'--add-data=web{os.pathsep}web',
        f'--add-data=locale{os.pathsep}locale',
        f'--add-data=src/themerr/migrations{os.pathsep}themerr/migrations',
        f'--add-data=jellyfin-connector{os.pathsep}jellyfin-connector',
        f'--add-binary={deno}{os.pathsep}.',
        '--icon=./web/images/favicon.ico'
    ]

    if sys.platform.lower() == 'win32':  # windows
        pyinstaller_args.append('--console')
        pyinstaller_args.append('--splash=./web/images/icon-default.png')

    elif sys.platform.lower() == 'darwin':  # macOS
        pyinstaller_args.append('--windowed')
        pyinstaller_args.append('--osx-bundle-identifier=dev.lizardbyte.app.themerr-plex')
        codesign_identity = os.environ.get('APPLE_CODESIGN_IDENTITY')
        if codesign_identity:
            pyinstaller_args.append(f'--codesign-identity={codesign_identity}')

    elif sys.platform.lower() == 'linux':  # linux
        pyinstaller_args.append('--splash=./web/images/icon-default.png')

    PyInstaller.__main__.run(pyinstaller_args)


if __name__ == '__main__':
    build()
