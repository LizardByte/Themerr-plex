:github_url: https://github.com/LizardByte/Themerr-plex/tree/nightly/docs/source/about/troubleshooting.rst

Troubleshooting
===============

Plugin Logs
-----------

See `Plugin Log Files <https://support.plex.tv/articles/201106148-channel-log-files/>`_ for the plugin
log directory.

Plex uses rolling logs. There will be six log files available. The newest log file will be named
``dev.lizardbyte.themerr-plex.log``. There will be additional log files with the same name, appended with a `1-5`.

It is best to replicate the issue you are experiencing, then review the latest log file. The information in the log
file may seem cryptic. If so it would be best to reach out for `support <https://app.lizardbyte.dev/support>`_.

.. Attention:: Before uploading logs, it would be wise to review the data in the log file. Plex does not filter
   the masked settings (e.g. credentials) out of the log file.

Plex Media Server Logs
----------------------

If you have a more severe problem, you may need to troubleshoot an issue beyond the plugin itself. See
`Plex Media Server Logs <https://support.plex.tv/articles/200250417-plex-media-server-log-files/>`_
for more information.
