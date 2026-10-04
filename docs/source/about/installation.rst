:github_url: https://github.com/LizardByte/Themerr-plex/blob/master/docs/source/about/installation.rst

Installation
============

Themerr-plex runs as a separate application alongside Plex Media Server. It does not use the Plex plug-in framework.
The application needs network access to Plex, ThemerrDB, and YouTube. To remove old plug-in behavior, stop Plex,
remove the old Themerr-plex bundle from its Plug-Ins directory, and restart Plex before starting the standalone app.

Release archive
---------------

Download the archive for your operating system and architecture from https://github.com/LizardByte/Themerr-plex/releases/latest.
Extract it and run the themerr_plex executable, or the themerr_plex.app bundle on macOS.
The macOS bundle stores configuration under ``~/Library/Application Support/Themerr-plex/config``.
Deno is bundled for yt-dlp's YouTube challenge solver. Open the web UI
at https://localhost:9494 to configure the Plex URL and sign in through Plex. Set the Plex data directory only if you want
to remove old uploaded media. The default web server uses a locally generated certificate, so your browser may ask you to trust it.

Docker
------

Docker images are available from Docker Hub and GitHub Container Registry. See :ref:`Docker <about/docker:docker>`
for volume and port settings.

Source
------

Install Python 3.14, uv, npm, and `Deno <https://docs.deno.com/runtime/getting_started/installation/>`_ 2.3 or newer.
Then run from the repository root:

.. code-block:: shell

   uv sync --locked
   uv run --locked python scripts/_locale.py --compile
   npm ci --ignore-scripts
   npm run build
   uv run --locked python src/themerr_plex.py

For a packaged build with web assets and documentation, see :ref:`Build <contributing/build:build>`.
