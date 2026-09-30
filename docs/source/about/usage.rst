:github_url: https://github.com/LizardByte/Themerr-plex/blob/master/docs/source/about/usage.rst

Usage
=====

Start Themerr-plex, then open its web UI at https://localhost:9494 (or the host and port you configured).
In Settings, enter and save your Plex server URL, then select **Sign in with Plex**. Complete the sign-in in the
Plex browser window and return to Settings. Themerr-plex checks the sign-in and connects to the configured server.
The Plex account must have access to that server. To change accounts, select **Disconnect Plex** and sign in again.
This replaces the manually entered Plex token used by older versions; existing installations must sign in once.
The resulting token is kept in the local Themerr SQLite database and is never shown in Settings.

Set the Plex data directory if you want Themerr-plex to remove older uploaded media from Plex's metadata directory.
Use the folder button beside this setting to browse directories on the machine running Themerr-plex. The same button
is available for the log directory.

When Themerr-plex runs on another machine, use the Plex server's reachable URL and mount its data directory if you
want this cleanup. Otherwise, disable the three **Remove unused** settings.

Enable movie, series, and collection updates as needed. Themerr-plex listens for supported Plex library
events and also scans on the configured schedule. The home page reports theme status for each supported
library item and links to ThemerrDB contribution forms when a TMDB ID is known. It shows an IMDb or TVDB ID when Plex
supplies one but a TMDB ID cannot be resolved. A Plex ID is shown for collections without a verified external ID;
Plex's ``collection://`` GUID is local to the server. Uploaded themes with no matching Themerr upload record are
labeled **Uploaded (source unknown)**. Themerr can replace these themes when a matching theme exists in ThemerrDB and
the overwrite settings allow it.

To exclude a library from scheduled updates, enter its ID in **Ignored library IDs** under advanced settings.
The home page shows each library's ID beside its name. Separate multiple IDs with commas.

TMDB IDs for titles already in ThemerrDB are resolved from ThemerrDB's index. Movie collections can also be resolved
from matching collection metadata on their member movies. To resolve other titles for a contribution link, set the optional
``TMDB_API_READ_ACCESS_TOKEN`` environment variable to your TMDB API Read Access Token. Keep this token outside the
web settings and configuration file.

Local data
----------

Themerr-plex stores its dashboard snapshot, upload records, processing errors, and Plex sign-in in
``themerr-plex.db`` beside the active configuration file (``config/themerr-plex.db`` by default, or
``/config/themerr-plex.db`` in Docker). Alembic applies schema migrations on startup.
Existing ``database_cache.json``, ``theme_errors.json``, ``plex-auth.json``, and per-item JSON records are copied into
SQLite on first use. The old files are left in place as backups and are no longer updated by Themerr-plex.

The /status endpoint returns a JSON health response. The /docs/ endpoint serves the documentation
bundled with packaged and Docker builds.

YouTube cookies
---------------

If YouTube rejects anonymous requests, export cookies from a browser in Chromium JSON format and enter the JSON in
the YouTube Cookies setting. Themerr-plex writes the cookies to a temporary Netscape file for yt-dlp and
removes that file after each extraction.

Theme format
------------

Themerr-plex selects the largest available Opus or MP4A audio stream. Enable Prefer MP4A AAC Codec for
Plex clients that cannot play Opus theme audio. If MP4A is unavailable, Opus is used.

.. note::

   A theme can only be added when its item exists in ThemerrDB. See
   :ref:`contributing/database <contributing/database:database>` to contribute a missing theme.
