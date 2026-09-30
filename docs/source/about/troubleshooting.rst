:github_url: https://github.com/LizardByte/Themerr-plex/blob/master/docs/source/about/troubleshooting.rst

Troubleshooting
===============

YouTube extraction
------------------

Themerr-plex uses yt-dlp for YouTube audio. YouTube may rate limit anonymous requests or require a signed-in
session for some videos. Export browser cookies in Chromium JSON format and place the JSON in the web UI's
YouTube Cookies setting. Test again after an item update or the next scheduled scan. If extraction still
fails, update the locked yt-dlp version and check the application log for the extractor error.
Themerr-plex selects an audio-only stream URL and does not require local FFmpeg for that extraction path.
An unavailable video is a separate YouTube error.

Plex connection
---------------

Check the Plex URL and connection status in Settings, and sign in through Plex again if needed. The configured Plex
data directory is needed for removing old
uploads; theme upload itself uses the Plex API. The Plex Movie and Plex Series agents are supported.
For an HTTPS Plex URL, the server certificate must be trusted. Set ``REQUESTS_CA_BUNDLE`` to a CA certificate file
when using a private certificate authority.
If theme uploads through a reverse proxy return an HTTP 504 gateway timeout, use a direct LAN Plex URL when the
application can reach the server on the local network, or increase the reverse proxy's upstream timeout. The
**PlexAPI timeout** setting controls how long Themerr-plex waits for Plex; it cannot extend a proxy's timeout.

Application logs
----------------

Logs are written under the application's config/logs directory, or under /config/logs in Docker.
Reproduce the problem, inspect the newest log, and remove tokens or cookies before sharing it. For Plex server
problems, see https://support.plex.tv/articles/200250417-plex-media-server-log-files/.
