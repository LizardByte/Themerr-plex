:github_url: https://github.com/LizardByte/Themerr-plex/blob/master/docs/source/about/usage.rst

Usage
=====

Start Themerr-plex, then open its web UI at https://localhost:9494 (or the host and port you configured).
In Settings, enter and save your Plex server URL, then select **Sign in with Plex**. Complete the sign-in in the
Plex browser window and return to Settings. Themerr-plex checks the sign-in and connects to the configured server.
The Plex account must have access to that server. To change accounts, select **Disconnect Plex** and sign in again.
This replaces the manually entered Plex token used by older versions; existing installations must sign in once.
On desktop systems, the Plex token is saved in the operating system's credential store and is never shown in Settings.
For Docker or headless systems, provide ``THEMERR_PLEX_TOKEN_KEY_FILE`` pointing to a persistent Fernet key file outside
the configuration directory. Themerr-plex uses that key to encrypt the token stored in SQLite. Keep the key file private;
losing it requires signing in again. Docker sign-in requires this key file.

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

Select the play button beside an item's title to listen to its currently selected Plex theme, regardless of provider.
The button changes to pause during playback, and the ring around it shows playback progress. Pausing retains your
position; selecting another item stops the previous theme. Items without an installed theme have no play button.

To exclude a library from scheduled updates, enter its ID in **Ignored library IDs** under advanced settings.
The home page shows each library's ID beside its name. Separate multiple IDs with commas.

TMDB IDs for titles already in ThemerrDB are resolved from ThemerrDB's index. Movie collections can also be resolved
from matching collection metadata on their member movies. Themerr-plex asks the configured Plex server's TMDB proxy to
resolve other IMDb or TVDB IDs and collection names. If the Plex proxy is unavailable, you can set the optional
``TMDB_API_READ_ACCESS_TOKEN`` environment variable to your TMDB API Read Access Token. Keep this token outside the
web settings and configuration file.

Local data
----------

Themerr-plex stores its dashboard snapshot, upload records, processing errors, and non-secret Plex client ID in
``themerr-plex.db`` beside the active configuration file (``config/themerr-plex.db`` by default, or
``/config/themerr-plex.db`` in Docker). Docker and headless installs also store the encrypted Plex token there.
Alembic applies schema migrations on startup. Existing ``database_cache.json``, ``theme_errors.json``, and per-item JSON
records are copied into SQLite on first use; those old files remain as backups. Any old plaintext Plex token row and
``plex-auth.json`` file are removed without importing the token, so you must sign in again.

The /status endpoint returns a JSON health response. The /docs/ endpoint serves the documentation
bundled with packaged and Docker builds.

YouTube cookies
---------------

Cookies are optional. They can help when YouTube asks you to sign in or rejects anonymous requests.
The **YouTube Cookies** setting accepts a JSON array of browser cookies. Paste the exported contents, including
the opening ``[`` and closing ``]``. A file path, a ``Cookie:`` request header, and Netscape ``cookies.txt`` contents
are not accepted by this setting.

For Chrome or another compatible Chromium browser:

1. Install `Get cookies.txt LOCALLY
   <https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc>`_,
   which is linked from the `yt-dlp cookie guide
   <https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp>`_.
   In the browser's extension settings, allow this extension in incognito/private windows.
2. Open a new incognito/private window and visit YouTube. Sign in if the video requires an account.
3. In that same tab, visit https://www.youtube.com/robots.txt. Keep it as the only tab in the private window.
4. Open the extension, set **Export Format** to **JSON**, and select **Copy** or **Export** for the current site.
   If you export a file, open it in a text editor and copy its entire contents. Avoid **Export All Cookies**;
   Themerr-plex only needs the YouTube cookies.
5. Close the private window. These steps follow `yt-dlp's YouTube export guidance
   <https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies>`_ to reduce cookie rotation.
6. In Themerr-plex, open **Settings** and find **YouTube Cookies** in the **Themerr** section. Paste the JSON and
   select **Save**. It will be used on the next extraction; a restart is not required.

If YouTube starts asking you to sign in again, repeat the export and replace the saved JSON.
Cookies cannot make a deleted or unavailable video accessible.

Treat cookies like passwords: they can grant access to your browser session. Keep the export and Themerr-plex
configuration private, and never include cookie values in screenshots, logs, or issue reports.
Themerr-plex converts the saved JSON to a temporary Netscape file for yt-dlp and removes that file after
each extraction; the JSON remains in the configuration until you clear the setting and save.

Theme format
------------

Themerr-plex selects the largest available Opus or MP4A audio stream. Enable Prefer MP4A AAC Codec for
Plex clients that cannot play Opus theme audio. If MP4A is unavailable, Opus is used.

.. note::

   A theme can only be added when its item exists in ThemerrDB. See
   :ref:`contributing/database <contributing/database:database>` to contribute a missing theme.
