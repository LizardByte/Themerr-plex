"""
scripts/build.py

Creates spec and builds binaries for Themerr-plex.
"""
# standard imports
import sys

# lib imports
import PyInstaller.__main__


def build():
    """Sets arguments for pyinstaller, creates spec, and builds binaries."""
    pyinstaller_args = [
        './src/themerr_plex.py',
        '--onefile',
        '--noconfirm',
        '--paths=./',
        '--add-data=docs:docs',
        '--add-data=web:web',
        '--add-data=locale:locale',
        '--icon=./web/images/favicon.ico'
    ]

    if sys.platform.lower() == 'win32':  # windows
        pyinstaller_args.append('--console')
        pyinstaller_args.append('--splash=./web/images/icon-default.png')

        # fix args for windows
        for index, arg in enumerate(pyinstaller_args):
            pyinstaller_args[index] = arg.replace(':', ';')
    elif sys.platform.lower() == 'darwin':  # macOS
        pyinstaller_args.append('--console')
        pyinstaller_args.append('--osx-bundle-identifier=dev.lizardbyte.themerr-plex')

    elif sys.platform.lower() == 'linux':  # linux
        pyinstaller_args.append('--splash=./web/images/icon-default.png')

    PyInstaller.__main__.run(pyinstaller_args)


if __name__ == '__main__':
    build()
