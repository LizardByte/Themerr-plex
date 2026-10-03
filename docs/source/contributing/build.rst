:github_url: https://github.com/LizardByte/Themerr-plex/blob/master/docs/source/contributing/build.rst

Build
=====

Themerr-plex uses Python 3.14, uv, npm, Deno, and Dockle. Python dependencies are specified in pyproject.toml and
resolved in uv.lock. The npm lockfile supplies reproducible web assets. esbuild bundles browser dependencies and local
scripts into ``web/assets``.

The browser interface and JSON API use FastAPI with Uvicorn. Uvicorn runs in the application's web thread and
uses the existing host, port, and TLS settings. Blocking Plex and database calls run in worker threads, while
theme audio streams through ASGI. The ``/docs/`` route serves the bundled project documentation.
Signed-in administrators can explore the API at ``/api/docs`` or retrieve its OpenAPI schema at
``/api/openapi.json``. The sidebar links to both kinds of documentation.

Translations are read directly from UTF-8 PO catalogs. No compilation is needed; source catalogs take precedence
over old MO files. Saving the language setting reloads the interface with the selected language.

From the repository root, install dependencies and build browser assets:

.. code-block:: shell

   uv sync --locked --all-extras
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
