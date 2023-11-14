:github_url: https://github.com/LizardByte/Themerr-plex/tree/nightly/docs/source/about/troubleshooting.rst

Troubleshooting
===============

Rate Limiting / Videos Not Downloading
--------------------------------------

By default, YouTube-DL will perform queries to YouTube anonymously. As a result, YouTube may rate limit the
requests, or sometimes simply block the content (e.g. for age-restricted content, but not only).

Adding your YouTube credentials (e-mail and password) in Themerr's preference may fix the problem. Hoewever,
YouTube also sometimes changes the way its login page works, preventing YouTube-DL from using those credentials.

A workaround is to login in a web browser, and then export your YouTube cookies with a tool such as `Get cookies.txt
locally <https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc>`__. Note 
that Themerr currently only supports Chromium's JSON export format. In the exporter you use, if prompted, you need to
use the "JSON" or "Chrome" format.

You can then paste that value in the "YouTube Cookies" field in the plugin preferences page. On the next media update
or scheduled run, the cookies will be used and hopefully videos will start downloading again.

Plugin Logs
-----------

See `Plugin Log Files <https://support.plex.tv/articles/201106148-channel-log-files/>`__ for the plugin
log directory.

Plex uses rolling logs. There will be six log files available. The newest log file will be named
``dev.lizardbyte.themerr-plex.log``. There will be additional log files with the same name, appended with a `1-5`.

It is best to replicate the issue you are experiencing, then review the latest log file. The information in the log
file may seem cryptic. If so it would be best to reach out for `support <https://app.lizardbyte.dev/support>`__.

.. Attention:: Before uploading logs, it would be wise to review the data in the log file. Plex does not filter
   the masked settings (e.g. credentials) out of the log file.

Plex Media Server Logs
----------------------

If you have a more severe problem, you may need to troubleshoot an issue beyond the plugin itself. See
`Plex Media Server Logs <https://support.plex.tv/articles/200250417-plex-media-server-log-files/>`__
for more information.
