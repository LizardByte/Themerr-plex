Build
=====

Themerr uses Python 3.14, uv, npm, Deno, and the .NET 10 SDK. Python dependencies are specified in pyproject.toml and
resolved in uv.lock. The npm lockfile supplies reproducible web assets. esbuild bundles browser dependencies and local
scripts into ``web/assets``.

The browser interface and JSON API use FastAPI with Uvicorn. Uvicorn runs in the application's web thread and
uses the existing host, port, and TLS settings. Blocking media-server and database calls run in worker threads, while
theme audio streams through ASGI. The application links to the hosted project documentation.
Signed-in administrators can explore the API at ``/api/docs`` or retrieve its OpenAPI schema at
``/api/openapi.json``. The sidebar links to both kinds of documentation.

Translations are read directly from UTF-8 PO catalogs. No compilation is needed; source catalogs take precedence
over old MO files. Saving the language setting reloads the interface with the selected language.

From the repository root, install dependencies and build browser assets:

.. code-block:: shell

   uv sync --locked --extra build --extra dev
   npm ci --ignore-scripts
   npm run build
   uv run --locked python scripts/build_connector.py

The connector builder produces separate Jellyfin 10.11 and 12.1 assemblies, targeting .NET 9 and .NET 10.
The .NET 10 SDK builds both targets; Jellyfin supplies their runtime dependencies. Generated ZIP archives and
their descriptor and catalog thumbnail live in the ignored ``jellyfin-connector`` directory. Rebuild them after
changing connector source, the thumbnail, or the Themerr version. To use a SDK outside ``PATH``, pass
``--dotnet /path/to/dotnet``.

Both connector builds use Themerr's release version mapped with the ``release_setup`` action's .NET scheme.
Dated versions split the ``HHMMSS`` component into ``HHMM`` and seconds, each with leading zeroes removed:
``2026.1005.51610`` becomes ``2026.1005.516.10``. Ordinary three-part versions append a zero revision;
four-part versions are preserved. Development builds use ``0.0.0.0`` rather than a separate timestamp.
The server-specific repository advertises only the matching Jellyfin ABI, and the source fingerprint verifies
the exact build even when release versions are equal.

The connector uses EF Core's SQLite provider and migrations, matching Jellyfin's SDK dependency versions:
9.0.10 for the 10.11 SDK and 10.0.11 for the 12.1 SDK. Runtime dependency assemblies are supplied by Jellyfin
and are excluded from the connector ZIP. ASP.NET Core supplies JSON serialization; the connector does not
manipulate JSON files.

Run the connector's file ownership and upload integrity checks with:

.. code-block:: shell

   dotnet run --project connectors/jellyfin.tests/Connector.Tests.csproj --configuration Release

Install the commit hook once per checkout:

.. code-block:: shell

   uv run --locked --no-sync pre-commit install

Before each commit, the hook extracts Python, JavaScript, and template messages into ``locale/themerr.po``.
If that file changes, the commit stops so you can review it, stage it with ``git add locale/themerr.po``,
and retry the commit. Unstaged edits are temporarily set aside while the hook checks the staged source.
The generated template omits creation and revision date headers and Babel's author placeholders. Its bug-report
URL points to the repository's GitHub issues page. Crowdin creates and updates the per-language catalogs under
``locale/<locale>/LC_MESSAGES/``. The application's language options are discovered from the available catalogs.

To extract the template manually:

.. code-block:: shell

   uv run --locked --no-sync python scripts/localize.py --extract

For local development, run ``scripts/run_dev.py`` with the project's Python interpreter. The wrapper installs locked
npm dependencies when needed, rebuilds changed browser assets,
and starts the Python source in the same process. Point an IDE debugger at this script to use normal breakpoints in
``src``. It uses Deno from ``PATH`` or ``.build-tools``; if Deno is unavailable, yt-dlp can use Node instead.

.. code-block:: shell

   uv run --locked --extra dev python scripts/run_dev.py --nolaunch

Build the standalone executable:

.. code-block:: shell

   uv run --locked --extra build python scripts/build.py

PyInstaller includes the web assets and translations in the
executable under dist, including Deno for yt-dlp and both Jellyfin connector archives. The standalone build
rebuilds the connectors after stamping the release version. CI builds both connectors once and shares the artifact
with all desktop packaging jobs. ``THEMERR_PREBUILT_CONNECTOR=1`` validates the artifact's source identity, release,
ABI and checksums instead of compiling again. macOS also produces ``dist/themerr.app``, a directory
bundle needed for native notifications. Set ``THEMERR_VERSION`` to the release version before running
``scripts/build.py`` to stamp ``src/common/version.py`` with the version used by release notifications and
``--version``. CI supplies this value from the release setup action's ``release_version`` output. The module
is included through normal imports. Unversioned builds compare releases against ``0.0.0``.

Read the Docs is the only documentation build service. It uses the checked-out
``third-party/dockle`` submodule's shared conda environment and build script. The shared script installs
Themerr's locked runtime and documentation dependencies for autodoc. Tool versions are declared in
Dockle's environment file. Python and the pinned Doxygen stay in the same environment. Documentation is
published online and is not bundled in Docker images or standalone executables.

For local documentation validation, initialize the submodules and create the documentation's conda
environment with pinned Doxygen and Graphviz versions:

.. code-block:: shell

   git submodule update --init --recursive
   conda env create --file third-party/dockle/environment.yml
   conda activate dockle-docs
   uv run --locked --extra docs python -m dockle check
   uv run --locked --extra docs python -m dockle build

Dockle writes the local site to ``_site``.

Dockle generates the connector's Doxygen XML before building Sphinx. Breathe and the pinned
``third-party/sphinx-csharp`` extension render its C# API alongside the Python reference, with links to
Jellyfin and Microsoft dependency documentation. Missing documentation, parameter descriptions, and
documentation warnings fail the build. Write C# XML comments for types and members, and use
``see``/``seealso`` references for related types. See :doc:`../src/jellyfin_connector` for the generated API.

Docker uses the same Python lockfile. A separate .NET stage uses uv to run the connector build script;
the runtime image contains their artifacts without the SDK:

.. code-block:: shell

   docker build -t themerr .
