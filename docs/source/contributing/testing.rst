:github_url: https://github.com/LizardByte/Themerr-plex/blob/master/docs/source/contributing/testing.rst

Testing
=======

Install the locked development dependencies and run the offline test suite from the repository root:

.. code-block:: shell

   uv sync --locked --extra dev
   uv run --locked --extra dev python -m pytest
   uv run --locked --extra dev python -m flake8

Tests use temporary files and mocked Plex, ThemerrDB, TMDb, and yt-dlp responses. No Plex server or
YouTube connection is needed. Coverage is configured in pyproject.toml and written to
coverage/python-coverage.xml.

For documentation validation, install the docs extra and build with Dockle:

.. code-block:: shell

   uv sync --locked --extra docs
   uv run --locked --extra docs python -m dockle check
   uv run --locked --extra docs python -m dockle build

Python API docstrings use NumPy style. Dockle runs numpydoc validation for project objects during the
strict documentation build.
