:github_url: https://github.com/LizardByte/Themerr-plex/blob/master/docs/source/about/usage.rst

Usage
=====

Start Themerr-plex, then open its web UI at https://localhost:9494 (or the host and port you configured).
In Settings, enter your Plex server URL and token. Set the Plex data directory if you want Themerr-plex to
remove older uploaded media from Plex's metadata directory.

Enable movie, series, and collection updates as needed. Themerr-plex listens for supported Plex library
events and also scans on the configured schedule. The home page reports theme status for each supported
library item and links to ThemerrDB contribution forms for missing themes.

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
