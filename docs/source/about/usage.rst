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

Preferences
-----------

Prefer MP4A AAC Codec
^^^^^^^^^^^^^^^^^^^^^

Description
   Some Plex clients, such as AppleTV, do not support the Opus audio codec for theme songs. This setting will
   force Themerr to select the MP4A AAC codec over the Opus codec when both are available. If the MP4A AAC codec is
   not available, the Opus codec will be used and the theme song will not be playable on clients that do not support
   the Opus codec.

Default
   True

PlexAPI Timeout
^^^^^^^^^^^^^^^

Description
   The timeout (in seconds) when uploading theme audio to the Plex server.

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

YouTube Username
^^^^^^^^^^^^^^^^

Description
   The YouTube Username to use. Supplying YouTube credentials will allow access to age restricted content.

Default
   None

YouTube Password
^^^^^^^^^^^^^^^^

Description
   The YouTube Password to use. Supplying YouTube credentials will allow access to age restricted content.

Default
   None
