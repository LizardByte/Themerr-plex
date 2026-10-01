:github_url: https://github.com/LizardByte/Themerr-plex/blob/master/docs/source/about/usage.rst

Usage
=====

Start Themerr-plex, then open its web UI at https://localhost:9494 (or the host and port you configured).

Admin account
-------------

On first start, Themerr-plex prints a one-time setup link in the console and opens it if browser launching is enabled.
Use this link to create the installation's single admin account with a password of at least 12 characters.
For a remote or Docker installation, replace ``127.0.0.1`` in the link with the reachable hostname, retaining the setup
token. Opening the normal address before setup shows instructions for obtaining this link.

The admin password is stored as a salted scrypt hash in SQLite. Sign in with this account to access libraries,
settings, server connections, theme playback, and bundled documentation. Sessions expire after 12 hours of inactivity and
restarting the application signs them out. Every form and modifying API request requires a CSRF token, and the
web UI cannot be embedded in an iframe.

Change your password under **Settings > Security**. This signs out other sessions. If you forget it, stop the
application and run its executable with ``--reset-admin-password`` from a local console. For a source checkout:

.. code-block:: shell

   uv run --locked python src/themerr_plex.py --reset-admin-password

Supply ``--config`` if you normally use a different configuration file. The command prompts for a new password
without echoing it and exits without starting the server.

Plex servers
------------

Open **Servers**, select **Sign in with Plex**, complete the sign-in in the Plex browser window, and return to Themerr.
The application admin account and your Plex account have separate roles: the former protects the web UI;
the latter authorizes access to your Plex servers. Plex sign-in is the only way to authorize a server connection.

Select **Find account servers** to list servers available to your account, including shared servers. Choose a
reachable address from the server's connection list and select **Connect**. Repeat for each server you want to manage.
You can also use **Discover on LAN** to find Plex's GDM announcements, or enter an HTTP or HTTPS base address
manually, such as ``http://192.168.1.10:32400``. Discovery and manual addresses still require access through your
signed-in Plex account. LAN discovery depends on multicast traffic reaching the machine running Themerr;
containers and separate subnets may need the manual address option.

Account discovery lists advertised addresses; it does not confirm that they are reachable. The connection list
labels local, remote, and relay addresses and their HTTP or HTTPS protocol. Plex's advertised ``https://...plex.direct``
addresses use its server certificate. Changing such an address to ``https://IP:32400`` can cause a certificate
mismatch. See `Plex secure connections <https://support.plex.tv/articles/206225077-how-to-use-secure-server-connections/>`_.
You can enter a known HTTP address manually if your Plex server allows insecure connections.

If LAN discovery finds nothing, check **Enable local network discovery (GDM)** in Plex's network settings and
whether multicast can reach Themerr's machine. If connecting times out, verify the chosen address and port are
reachable from that machine, including its firewall and network route. Re-pairing Plex will not fix an unreachable
server address.

Each saved server has its own processing toggle, ignored library IDs, data directory, dashboard snapshot,
upload history, and errors. Pausing a server prevents new work; an upload already in progress can finish.
Removing a server erases its saved connection and local records, while themes already uploaded to Plex remain there.
Select **Disconnect Plex** to erase Plex credentials and pause saved servers. After signing in again, reconnect
each server to resume processing with its retained upload history.

On desktop systems, account and server tokens are saved in the operating system's credential store.
For Docker or headless systems, provide ``THEMERR_PLEX_TOKEN_KEY_FILE`` pointing to a persistent Fernet key file outside
the configuration directory. Themerr-plex uses that key to encrypt tokens stored in SQLite. Keep the key file private;
losing it requires signing in again. Docker sign-in requires this key file.

Expand **Processing settings** on a server card to set its Plex data directory if you want Themerr-plex to remove
older uploaded media from Plex's metadata directory. Use the folder button to browse directories on the machine
running Themerr-plex. The same button is available for the log directory in Settings.

When Themerr-plex runs on another machine, use the Plex server's reachable URL and mount its data directory if you
want this cleanup. Otherwise, disable the three **Remove unused** settings.

Enable movie, series, and collection updates as needed. Themerr-plex listens for supported Plex library
events and also scans on the configured schedule. The home page reports theme status for each supported
library item and links to ThemerrDB contribution forms when a TMDB ID is known. It shows an IMDb or TVDB ID when Plex
supplies one but a TMDB ID cannot be resolved. A Plex ID is shown for collections without a verified external ID;
Plex's ``collection://`` GUID is local to the server. Themes with no matching provider or Themerr upload record are
labeled **Unknown provider**. Themerr can replace these themes when a matching theme exists in ThemerrDB and
the overwrite settings allow it.

Use the Overview search and server, type, and status filters to find individual items. **Refresh libraries** updates
the dashboard and reloads the page when the refresh finishes, retaining those filters. Active theme playback is
preserved instead of reloading; the completion message tells you when the new snapshot is ready.
**Activity** shows scheduled task starts, completion, duration, the upload queue, and per-item failure reasons.
Its **Scan for themes** button also starts a processing scan when theme updates are enabled.

The search field's clear button removes just the title search, retaining the other filters. Plex and metadata IDs
open the item on Plex or its metadata provider in a new tab. Media type icons remain visible beside theme playback.
**Edit** appears for source video issues such as removal, privacy, or age restrictions. Local network, upload, and
regional failures do not by themselves require replacing the ThemerrDB video. ThemerrDB checks US availability
when accepting themes; a regional failure elsewhere cannot establish that it is currently unavailable in the US.

Select the play button beside an item's title to listen to its currently selected Plex theme, regardless of provider.
The button changes to pause during playback, and the ring around it shows playback progress. Pausing retains your
position; selecting another item stops the previous theme. Items without an installed theme have no play button.

To exclude a library from updates, enter its ID in **Ignored library IDs** in its server's processing settings.
The home page shows each library's ID beside its name. Separate multiple IDs with commas.

TMDB IDs for titles already in ThemerrDB are resolved from ThemerrDB's index. Movie collections can also be resolved
from matching collection metadata on their member movies. Themerr-plex asks the item's Plex server's TMDB proxy to
resolve other IMDb or TVDB IDs and collection names. If the Plex proxy is unavailable, you can set the optional
``TMDB_API_READ_ACCESS_TOKEN`` environment variable to your TMDB API Read Access Token. Keep this token outside the
web settings and configuration file.

Local data
----------

Themerr-plex stores its server registry, admin password hash, dashboard snapshots, upload records, processing errors,
and non-secret Plex client ID in
``themerr-plex.db`` beside the active configuration file (``config/themerr-plex.db`` by default, or
``/config/themerr-plex.db`` in Docker). Docker and headless installs also store encrypted Plex tokens there.
Alembic applies schema migrations on startup. Existing ``database_cache.json``, ``theme_errors.json``, and per-item JSON
records are copied into SQLite on first use; those old files remain as backups. Any old plaintext Plex token row and
``plex-auth.json`` file are removed without importing the token, so you must sign in again.
The former single-server connection is adopted on startup when its saved authorization still works; its existing
upload history is kept. Otherwise, reconnect the server from the Servers page.

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
   select **Save changes**. It will be used on the next extraction; a restart is not required.

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

Before uploading, Themerr-plex downloads the complete audio with yt-dlp, decodes it to check its duration and codec,
and uploads the local file to Plex. It then verifies that Plex serves the same bytes. Validation uses PyAV's bundled
FFmpeg libraries; a separate FFmpeg installation is not needed. Temporary downloads and cookies are deleted afterward.

Themes previously uploaded by Themerr through a remote audio URL are replaced once using this verified file upload.
This repairs potentially truncated themes. Locked themes and the setting for preserving Plex-provided themes still
apply. Successful file uploads are recorded in SQLite and are skipped on later jobs unless the source changes or
the AAC preference requires a different codec. A failed replacement does not delete the previous theme file or
overwrite its tracking record.

.. note::

   A theme can only be added when its item exists in ThemerrDB. See
   :ref:`contributing/database <contributing/database:database>` to contribute a missing theme.
