:github_url: https://github.com/LizardByte/Themerr-plex/tree/nightly/docs/source/about/usage.rst

Usage
=====

Minimal setup is required to use Themerr-plex. In addition to the installation, a couple of settings must be configured.

   #. Navigate to the `Plugins` menu within the Plex server settings.
   #. Select the gear cog when hovering over the Themerr-plex plugin tile.
   #. Set the values of the preferences and save.

      .. Warning:: Plex stores configuration values in the log. If you upload your logs for support, it would be wise to
         review the data in the log file.

   #. For legacy agents and plugins, enable `Themerr-plex` in your agent settings. This is not necessary for the
      new Plex Movie agent.
   #. Refresh Metadata

.. Note:: If a movie's metadata was refreshed and no theme song was added, it is most likely that the movie is not in
   the database. Please see :ref:`contributing/database <contributing/database:database>` for information on how to
   contribute.

.. Attention:: It may take several minutes after completing a metadata refresh for a theme song to be available.

Web UI
------

A web interface is provided by the plugin. Currently the web ui only provides a couple of end points.

/ (root)
^^^^^^^^

This endpoint will display a report showing the theme song status for each item in a library supported by Themerr-plex.
A supported library is any that has the default agent as one supported by Themerr-plex.

The report provides an easy means to contribute to `ThemerrDB <https://github.com/LizardByte/ThemerrDB>`__ by providing
`Add/Edit` buttons for items that can be added to ThemerrDB.

/status
^^^^^^^

An endpoint that provides a JSON response. If a valid response is returned, Themerr-plex is running.

**Example Response**

.. code-block:: json

   {
     "message":"Ok",
     "result":"success"
   }

Preferences
-----------

Plex Movie agent support
^^^^^^^^^^^^^^^^^^^^^^^^

Description
   When enabled, Themerr-plex will add themes to movies using the Plex Movie agent. This is the new agent that is
   not using the Plex plugin framework, so Themerr-plex cannot contribute to this agent with standard techniques.
   Instead Themerr-plex will start a websocket server and listen for events from the Plex server. Whenever a movie
   is added or has it's metadata refreshed, Themerr-plex will attempt to add a theme song to the movie (if the theme
   song is available in ThemerrDB).

Default
   ``True``

Prefer MP4A AAC Codec
^^^^^^^^^^^^^^^^^^^^^

Description
   Some Plex clients, such as AppleTV, do not support the Opus audio codec for theme songs. This setting will
   force Themerr to select the MP4A AAC codec over the Opus codec when both are available. If the MP4A AAC codec is
   not available, the Opus codec will be used and the theme song will not be playable on clients that do not support
   the Opus codec.

Default
   ``True``

Remove unused theme songs
^^^^^^^^^^^^^^^^^^^^^^^^^

Description
   When Themerr-plex uploads a theme song to the Plex server, it will remove any existing theme songs for the same
   item. With this setting enabled, Themerr-plex can free up space in Plex's metadata directory. This will only remove
   items that were uploaded by Themerr-plex or via the hidden Plex rest API method, it will not affect local media
   assets.

Default
   ``True``

Remove unused art
^^^^^^^^^^^^^^^^^

Description
   When Themerr-plex uploads art to the Plex server, it will remove any existing art for the same
   item. With this setting enabled, Themerr-plex can free up space in Plex's metadata directory. This will only remove
   items that are user uploaded, it will not affect items added by metadata agents or local media assets.

Default
   ``False``

Remove unused posters
^^^^^^^^^^^^^^^^^^^^^

Description
   When Themerr-plex uploads posters to the Plex server, it will remove any existing posters for the same
   item. With this setting enabled, Themerr-plex can free up space in Plex's metadata directory. This will only remove
   items that are user uploaded, it will not affect items added by metadata agents or local media assets.

Default
   ``False``

Automatically update items
^^^^^^^^^^^^^^^^^^^^^^^^^^

Description
   When enabled, Themerr-plex will periodically check for changes in ThemerrDB and apply the changes to the items in
   your Plex Media Server automatically.

Default
   ``True``

Update movie themes during automatic update
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Description
   When enabled, Themerr-plex will update movie themes during automatic updates.

Default
   ``True``

Update collection themes during automatic update
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Description
   When enabled, Themerr-plex will update collection themes during automatic updates.

Default
   ``True``

Update collection metadata for Plex Movie agent
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Description
   When enabled, Themerr-plex will update collection metadata for the Plex Movie agent during automatic updates.
   Requires ``Update collection themes during automatic update`` to be enabled.

Default
   ``False``

Update collection metadata for legacy agents
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Description
   When enabled, Themerr-plex will update collection metadata for legacy agents during automatic updates. Themerr-plex
   must also be enabled in the agent settings.
   Requires ``Update collection themes during automatic update`` to be enabled.

Default
   ``True``

Interval for automatic update task
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Description
   The interval (in minutes) to run the automatic update task.

Default
   ``60``

Minimum
   ``15``

Interval for database cache update task
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Description
   The interval (in minutes) to run the database cache update task. This data is used to display the Web UI dashboard.

Default
   ``60``

Minimum
   ``15``

PlexAPI Timeout
^^^^^^^^^^^^^^^

Description
   The timeout (in seconds) when uploading media to the Plex server.

Default
   ``180``

Minimum
   ``1``

Max Retries
^^^^^^^^^^^

Description
   The number of times to retry uploading theme audio to the Plex server. The time between retries will increase
   exponentially. The time between is calculated as ``2 ^ retry_number``. For example, the first retry will occur
   after 2 seconds, the second retry will occur after 4 seconds, and the third retry will occur after 8 seconds.

Default
   ``6``

Minimum
   ``0``

Multiprocessing Threads
^^^^^^^^^^^^^^^^^^^^^^^

Description
   The number of simultaneous themes to upload for libraries using the Plex Movie agent. Does not apply to legacy
   agents or plugin agents.

Default
   ``3``

Minimum
   ``1``

YouTube Cookies
^^^^^^^^^^^^^^^^

Description
   The cookies to use for the requests to YouTube. Should be in Chromium JSON export format.
   `Example exporter <https://chrome.google.com/webstore/detail/get-cookiestxt/bgaddhkoddajcdgocldbbfleckgcbcid>`__.

Default
   None

Web UI Locale
^^^^^^^^^^^^^

Description
   The localization value to use for translations.

Default
   ``en``

Web UI Host Address
^^^^^^^^^^^^^^^^^^^

Description
   The host address to bind the Web UI to.

.. Attention::
   Changing this value requires a Plex Media Server restart.

Default
   ``0.0.0.0``

Web UI Port
^^^^^^^^^^^

Description
   The port to bind the Web UI to.

.. Attention::
   Changing this value requires a Plex Media Server restart.

Default
   ``9494``

Log all web server messages
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Description
   If set to ``True``, all web server messages will be logged. This will include logging requests and status codes when
   requesting any resource. It is recommended to keep this disabled unless debugging.

.. Attention::
   Changing this value requires a Plex Media Server restart.

Default
   ``False``

Migrate from < v0.3.0
^^^^^^^^^^^^^^^^^^^^^

Description
   Prior to v0.3.0, Themerr-plex uploaded themes were locked and there was no way to determine if a theme was supplied
   by Themerr-plex. Therefore, if you used Themerr-plex prior to v0.3.0, you will need to enable this setting to
   automatically unlock all existing themes (for agents that Themerr-plex supports). Once the migration has completed,
   the unlock function will never run again.

   If you see many of the ``Unknown provider`` status in the web UI, it is a good indication that you need to enable
   this option, unless you have many themes provided by other tools.

Default
   ``False``
