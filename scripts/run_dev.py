"""Prepare local assets and run Themerr-plex in this Python process for debugging."""

# standard imports
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def _asset_sources() -> list[Path]:
    """List inputs that require rebuilding the browser bundle.

    Returns
    -------
    list[Path]
        Web source files and build manifests.
    """
    return [
        *ROOT.joinpath('web', 'js').rglob('*.js'),
        *ROOT.joinpath('web', 'css').rglob('*.css'),
        ROOT / 'scripts' / 'build-assets.mjs',
        ROOT / 'package.json',
        ROOT / 'package-lock.json',
    ]


def _assets_need_build() -> bool:
    """Check whether the local browser bundle is missing or older than its inputs.

    Returns
    -------
    bool
        True when ``npm run build`` is needed.
    """
    outputs = [
        ROOT / 'web' / 'assets' / name
        for name in (
            'app.js',
            'app.css',
            'api_docs.js',
            'api_docs.css',
        )
    ]
    if any(not output.is_file() for output in outputs):
        return True
    oldest_output = min(output.stat().st_mtime_ns for output in outputs)
    return any(source.stat().st_mtime_ns > oldest_output for source in _asset_sources())


def _ensure_assets() -> None:
    """Install locked npm dependencies and build changed browser assets."""
    lockfile = ROOT / 'package-lock.json'
    install_marker = ROOT / 'node_modules' / '.package-lock.json'
    installed = install_marker.is_file() and install_marker.stat().st_mtime_ns >= lockfile.stat().st_mtime_ns
    if installed and not _assets_need_build():
        return

    npm = shutil.which('npm')
    if not npm:
        raise SystemExit('npm is required to build browser assets. Install Node.js and try again.')

    if not installed:
        subprocess.run(
            [
                npm,
                'ci',
                '--ignore-scripts',
            ],
            cwd=ROOT,
            check=True,
        )
    subprocess.run(
        [
            npm,
            'run',
            'build',
        ],
        cwd=ROOT,
        check=True,
    )


def _docs_need_build() -> bool:
    """Check whether bundled documentation is missing or stale.

    Returns
    -------
    bool
        True when Dockle should rebuild the site.
    """
    site_index = ROOT / '_site' / 'index.html'
    if not site_index.is_file():
        return True
    built_at = site_index.stat().st_mtime_ns
    sources = [
        *ROOT.joinpath('docs', 'source').rglob('*'),
        *ROOT.joinpath('connectors', 'jellyfin').glob('*.cs'),
        ROOT / 'connectors' / 'jellyfin' / 'Themerr.Connector.csproj',
        *ROOT.joinpath('docs').glob('*.py'),
        ROOT / 'docs' / 'environment.yml',
        ROOT / 'dockle.toml',
    ]
    return any(source.is_file() and source.stat().st_mtime_ns > built_at for source in sources)


def _ensure_docs() -> None:
    """Build changed documentation when Dockle is installed."""
    if not _docs_need_build():
        return
    if importlib.util.find_spec('dockle') is None:
        print('Documentation is unavailable; install the docs extra to build it.', file=sys.stderr)
        return
    subprocess.run(
        [
            sys.executable,
            '-m',
            'dockle',
            'build',
        ],
        cwd=ROOT,
        check=True,
    )


def _has_js_runtime() -> bool:
    """Check for Deno or Node for yt-dlp's YouTube challenge solver.

    Returns
    -------
    bool
        Whether a supported runtime is available to source builds.
    """
    deno_name = 'deno.exe' if sys.platform == 'win32' else 'deno'
    return bool(shutil.which('deno') or (ROOT / '.build-tools' / deno_name).is_file() or shutil.which('node'))


def main() -> None:
    """Prepare resources and launch the app in the debugger's Python process."""
    os.chdir(ROOT)
    _ensure_assets()
    _ensure_docs()
    if not _has_js_runtime():
        print('No Deno or Node runtime found; YouTube extraction may be incomplete.', file=sys.stderr)

    sys.path.insert(0, str(ROOT / 'src'))
    from themerr_plex import main as app_main

    app_main()


if __name__ == '__main__':
    main()
