:github_url: https://github.com/LizardByte/Themerr-plex/tree/nightly/docs/source/about/usage.rst

Usage
=====

Minimal setup is required to use Themerr-plex. In addition to the installation, a couple of settings must be configured.

   #. Navigate to the `Plugins` menu within the Plex server settings.
   #. Select the gear cog when hovering over the Themerr-plex plugin tile.
   #. Set the values of the preferences and save.
   #. Enable `Themerr-plex` in your agent settings.
   #. Refresh Metadata

.. Note:: If a movie's metadata was refreshed and no theme song was added, it is most likely that the movie is not in
   the database. Please see :ref:`contributing/database <contributing/database:database>` for information on how to
   contribute.

.. Attention:: It may take several minutes after completing a metadata refresh for a theme song to be available.

Preferences
-----------

PlexAPI Timeout
^^^^^^^^^^^^^^^

Description
   The timeout (in seconds) when uploading theme audio to the Plex server.

Default
   ``180``

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

Plex Server URL
^^^^^^^^^^^^^^^

Description
   The URL to use for accessing the Plex server. Themerr-plex uses `python-plexapi` to upload theme songs, so must have
   access to the Plex URL.

Default
   ``http://localhost:32400``

Plex token
^^^^^^^^^^

Description
   The token to use for accessing the Plex server. Themerr-plex uses `python-plexapi` to upload theme songs, so this
   must be set.

   .. Tip:: See `Finding an authentication token / X-Plex-Token
      <https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token>`_.

Default
   None
