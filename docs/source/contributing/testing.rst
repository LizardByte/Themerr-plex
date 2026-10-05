:github_url: https://github.com/LizardByte/Themerr-plex/blob/master/docs/source/contributing/testing.rst

Testing
=======

Install the locked development dependencies and run the offline test suite from the repository root:

.. code-block:: shell

   uv sync --locked --extra dev
   uv run --locked --extra dev python -m pytest
   uv run --locked --extra dev python -m flake8
   npm ci
   npm run build
   npm test

Tests use temporary files and mocked Plex, ThemerrDB, TMDb, and yt-dlp responses. No Plex server or
YouTube connection is needed. Coverage is configured in pyproject.toml and written to
coverage/python-coverage.xml.

Authentication tests exercise real signed sessions, CSRF checks, password hashing, throttling, and password changes.
Multi-server tests use colliding library and rating keys to check database, credentials, event listeners, workers,
metadata lookups, and theme playback isolation. Browser playback and dashboard filtering have offline Node tests.
Use an isolated configuration file for manual browser testing so sample data and credentials do not affect your
normal installation.

Connector tests run the same xUnit suite against Jellyfin 10.11 and 12.1. Install the .NET 10 SDK and
the .NET 9 and 10 ASP.NET Core runtimes, then run:

.. code-block:: shell

   uv run --no-project --python 3.14 scripts/test_connector.py

The script writes OpenCover coverage and JUnit test reports into separate ``coverage/connector-*`` directories.
Use ``--output`` to place reports outside the checkout. CI uploads both profiles to Codecov. Tests use temporary
item directories and mocked Jellyfin services; no running media server is required.

The connector and its tests use the repository's ``.editorconfig`` and the Sonar and StyleCop analyzers
configured in ``connectors/Directory.Build.props``. Analyzer warnings fail compilation. CI also rejects
formatting changes; run the same checks locally with:

.. code-block:: shell

   dotnet format connectors/jellyfin/Themerr.Connector.csproj --verify-no-changes
   dotnet format connectors/jellyfin.tests/Connector.Tests.csproj --verify-no-changes

For documentation validation, initialize the documentation submodules, create the conda environment,
and install the docs extra. See :doc:`build` for the complete build setup:

.. code-block:: shell

   git submodule update --init --recursive
   conda env create --file third-party/dockle/environment.yml
   conda activate dockle-docs
   uv sync --locked --extra docs
   uv run --locked --extra docs python -m dockle check
   uv run --locked --extra docs python -m dockle build

Python API docstrings use NumPy style. Dockle runs numpydoc validation for project objects during the
strict documentation build.
The connector uses XML documentation comments; strict Doxygen and C# compilation reject undocumented
types and members. Sphinx checks references to Jellyfin and Microsoft dependency documentation.
