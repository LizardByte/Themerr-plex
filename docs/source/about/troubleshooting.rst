Troubleshooting
===============

YouTube extraction
------------------

Themerr uses yt-dlp for YouTube audio. YouTube may rate limit anonymous requests or require a signed-in
session for some videos. Follow :ref:`the cookie export steps <about/usage:YouTube cookies>` and paste the entire
JSON export in the web UI's **YouTube Cookies** setting. Select **JSON** in the exporter; Netscape text and
cookie file paths are not accepted by this setting. If saved cookies stop working, export a fresh session.
Test again after an item update or the next scheduled scan. If extraction still
fails, update the locked yt-dlp version and check the application log for the extractor error.
Themerr selects an audio-only stream URL and does not require local FFmpeg for that extraction path.
An unavailable video is a separate YouTube error.
The home page shows the latest recorded extraction or upload failure beside the affected item. A theme that is listed
in ThemerrDB but has not been installed and has no recorded failure is shown as **Theme not installed yet**.

Plex connection
---------------

Check the Plex URL and connection status in Settings, and sign in through Plex again if needed. The configured Plex
data directory is needed for removing old
uploads; theme upload itself uses the Plex API. The Plex Movie and Plex Series agents are supported.
For an HTTPS Plex URL, the server certificate must be trusted. Set ``REQUESTS_CA_BUNDLE`` to a CA certificate file
when using a private certificate authority.
If theme uploads through a reverse proxy return an HTTP 504 gateway timeout, use a direct LAN Plex URL when the
application can reach the server on the local network, or increase the reverse proxy's upstream timeout. The
**PlexAPI timeout** setting controls how long Themerr waits for Plex; it cannot extend a proxy's timeout.

Application logs
----------------

Logs are written under the application's config/logs directory, or under /config/logs in Docker.
The three active files are ``themerr.log``, ``backend.log``, and ``yt-dlp.log``, with up to five rotated backups
per file at 5 MB each. Existing files from older versions are retained; the viewer reads the three active channels.
Open **Logs** in the web UI to search recent messages, filter by source or severity, jump between warnings and
errors, and download the filtered records. If the log directory is unavailable, restore its permissions or
select **Since startup** to inspect the temporary current-session history. That history survives file rotation
and is released when Themerr exits. If temporary storage is unavailable, the viewer reports the unavailable sources;
inspect the console output. Reproduce the problem and review logs for tokens or cookies before sharing them.
For Plex server problems, see https://support.plex.tv/articles/200250417-plex-media-server-log-files/.
