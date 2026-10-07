"""
scripts/build.py

Creates spec and builds binaries for Themerr.
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


def _deno_binary():
    """Locate Deno for native builds, including the local build-tools fallback."""
    deno = shutil.which('deno')
    if deno is not None:
        return deno

    executable = 'deno.exe' if sys.platform == 'win32' else 'deno'
    local_deno = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.build-tools', executable)
    if not os.path.isfile(local_deno):
        raise SystemExit('Deno is required to bundle yt-dlp YouTube support.')
    return local_deno


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
    pyinstaller_args = [
        './src/main.py',
        '--name=themerr',
        '--onedir' if sys.platform == 'darwin' else '--onefile',
        '--noconfirm',
        '--paths=./src',
        '--collect-all=av',
        '--hidden-import=uvicorn.loops.asyncio',
        '--hidden-import=uvicorn.protocols.http.h11_impl',
        '--hidden-import=uvicorn.lifespan.off',
        f'--add-data=web{os.pathsep}web',
        f'--add-data=locale{os.pathsep}locale',
        f'--add-data=src/themerr/migrations{os.pathsep}themerr/migrations',
        f'--add-data=jellyfin-connector{os.pathsep}jellyfin-connector',
        f'--add-data=src/jellyfin/compatibility.props{os.pathsep}jellyfin',
        '--icon=./web/images/favicon.ico',
    ]

    # Docker supplies Deno separately to isolate its glibc libraries from musl.
    docker = bool(os.getenv('THEMERR_DOCKER'))
    if not docker:
        pyinstaller_args.append(f'--add-binary={_deno_binary()}{os.pathsep}.')

    if sys.platform.lower() == 'win32':  # windows
        pyinstaller_args.append('--console')
        pyinstaller_args.append('--splash=./web/images/icon-default.png')

    elif sys.platform.lower() == 'darwin':  # macOS
        pyinstaller_args.append('--windowed')
        pyinstaller_args.append('--osx-bundle-identifier=dev.lizardbyte.app.themerr')
        codesign_identity = os.environ.get('APPLE_CODESIGN_IDENTITY')
        if codesign_identity:
            pyinstaller_args.append(f'--codesign-identity={codesign_identity}')

    elif sys.platform.lower() == 'linux' and not docker:  # linux desktop
        pyinstaller_args.append('--splash=./web/images/icon-default.png')

    PyInstaller.__main__.run(pyinstaller_args)


if __name__ == '__main__':
    build()
