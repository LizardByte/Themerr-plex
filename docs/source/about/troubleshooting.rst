:github_url: https://github.com/LizardByte/Themerr-plex/blob/master/docs/source/about/troubleshooting.rst

Troubleshooting
===============

YouTube extraction
------------------

Themerr-plex uses yt-dlp for YouTube audio. YouTube may rate limit anonymous requests or require a signed-in
session for some videos. Export browser cookies in Chromium JSON format and place the JSON in the web UI's
YouTube Cookies setting. Test again after an item update or the next scheduled scan. If extraction still
fails, update the locked yt-dlp version and check the application log for the extractor error.

Plex connection
---------------

Check the Plex URL and token in the web UI. The configured Plex data directory is needed for removing old
uploads; theme upload itself uses the Plex API. The Plex Movie and Plex Series agents are supported.

Application logs
----------------

Logs are written under the application's config/logs directory, or under /config/logs in Docker.
Reproduce the problem, inspect the newest log, and remove tokens or cookies before sharing it. For Plex server
problems, see https://support.plex.tv/articles/200250417-plex-media-server-log-files/.
