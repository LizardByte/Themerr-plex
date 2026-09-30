:github_url: https://github.com/LizardByte/Themerr-plex/blob/master/docs/source/contributing/build.rst

Build
=====

Themerr-plex uses Python 3.14, uv, npm, Deno, and Dockle. Python dependencies are specified in pyproject.toml and
resolved in uv.lock. The npm lockfile supplies reproducible web assets. esbuild bundles browser dependencies and local
scripts into ``web/assets``.

From the repository root, install dependencies and compile translations:

.. code-block:: shell

   uv sync --locked --all-extras
   uv run --locked --all-extras python scripts/_locale.py --compile
   npm ci --ignore-scripts
   npm run build

For local development, run ``scripts/run_dev.py`` with the project's Python interpreter. The wrapper installs locked
npm dependencies when needed, rebuilds changed browser assets and documentation when Dockle is available,
and starts the Python source in the same process. Point an IDE debugger at this script to use normal breakpoints in
``src``. It uses Deno from ``PATH`` or ``.build-tools``; if Deno is unavailable, yt-dlp can use Node instead.

.. code-block:: shell

   uv run --locked --all-extras python scripts/run_dev.py --nolaunch

Build the documentation and standalone executable:

.. code-block:: shell

   uv run --locked --all-extras python -m dockle check
   uv run --locked --all-extras python -m dockle build
   uv run --locked --all-extras python scripts/build.py

Dockle writes the site to _site. PyInstaller includes that site, the web assets, and translations in the
executable under dist, including Deno for yt-dlp. Docker uses the same lockfile and Dockle build:

.. code-block:: shell

   docker build -t themerr-plex .
