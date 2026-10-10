MCP integration
===============

Themerr embeds a Model Context Protocol (MCP) server at ``https://localhost:9494/mcp``.
Use the host, port, and HTTP or HTTPS scheme configured for your installation.
It runs inside the application's web server and uses Streamable HTTP with JSON responses.
By default, it shares the administrator UI's listening port.

HTTP for local clients
----------------------

Clients that do not trust Themerr's default self-signed certificate can use the existing companion HTTP port.
In **Settings > MCP integration**, enable **Serve MCP over HTTP**, save, and restart Themerr.
The endpoint URL in the MCP card then uses ``http://localhost:9495/mcp`` (with your current host and configured port).
The HTTPS MCP endpoint remains available.

This option defaults to disabled and shares **Settings > Jellyfin > Connector HTTP port**, which defaults to
``9495``. Set a nonzero port different from the administrator UI port. The companion listener serves fixed
connector downloads and authenticated MCP requests; it does not expose the administrator UI or token-management
API. If the administrator UI already uses HTTP, its existing ``/mcp`` endpoint can be used directly.

Both endpoints require the same bearer tokens and enforce the same scopes, revocation, request limits, and
Host/Origin allowlists. Use this HTTP option for local clients; use trusted HTTPS for remote connections.

Client authentication
---------------------

Sign in to Themerr and open **Settings > MCP integration**. Give the token a name identifying your client,
choose its scope, and select **Create token**. Copy the token shown in the panel into your MCP client's
credential settings using **Copy token**. The token starts masked; **Show token** and **Mask token** control
its visibility. It is available only after creation and cannot be retrieved later. The same page displays
the endpoint URL and lists issued tokens with their names, scopes, creation times, and validity.

Configure your client to connect to the ``/mcp`` URL over Streamable HTTP and send this header on every request:

.. code-block:: text

   Authorization: Bearer <your-token>

Tokens have two scopes:

* ``read`` allows server and library discovery, searches, coverage, theme inspection, ThemerrDB lookups, activity, and logs.
* ``process`` allows the same queries plus library refreshes and selected-item retries.

Browser sessions and media-server credentials do not authorize MCP requests. Tokens are independent of
application restarts; only their SHA-256 digests are stored. Changing or resetting the administrator password
invalidates previously issued tokens. Select **Revoke** beside a client to invalidate that token immediately,
or **Revoke all tokens** to disconnect every MCP client.
An MCP token authorizes access to the installation's saved media servers. There are no server-specific scopes.
Clients must support an explicitly configured bearer header; OAuth registration and login are not provided.

Remote connections
------------------

By default, the MCP Host allowlist permits ``localhost``, ``127.0.0.1``, and ``[::1]`` on any port.
For access through another address, open **Settings > Network > MCP allowed hosts**, enter the addresses your
clients will use, and restart Themerr. For example:

.. code-block:: text

   localhost:9494,127.0.0.1:9494,192.168.1.10:9494,themerr.example:443

The comma-separated values are HTTP Host headers, including ports when present. They replace the default
allowlist. A value ending in ``:*`` allows that host on any port. Requests with an Origin header must match
one of these hosts with an HTTP or HTTPS scheme. Reverse proxies must preserve an allowed Host header;
forwarded headers do not alter the validation. Use HTTPS for bearer credentials on remote networks.
Container deployments can override this setting with the ``THEMERR_MCP_ALLOWED_HOSTS`` environment variable.

Available tools
---------------

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Tool
     - Purpose
   * - ``list_servers``
     - Saved server identifiers, enablement, ignored libraries, and last refresh state. No credentials or directories.
   * - ``list_libraries``
     - Cached library names and identifiers, including paused or offline servers.
   * - ``search_items``
     - Filter cached items by title, server, library, media type, year, theme status, or provider.
   * - ``get_theme_coverage``
     - Installed counts, percentage, and status counts, optionally scoped to a server or library.
   * - ``inspect_theme``
     - Cached metadata identifiers, installed provider, recorded processing error, and successful upload tracking.
   * - ``check_themerrdb``
     - Check whether a movie, show, or collection exists in ThemerrDB using a TMDB ID, or an IMDb ID for a movie.
   * - ``get_activity``
     - Recent dispatch jobs and separate counts for queued and active uploads.
   * - ``get_logs``
     - Bounded, redacted recent logs or a page of current-session history, filtered by source, severity, and message.
   * - ``refresh_libraries``
     - Refresh metadata for enabled servers and return a dispatch job ID. Requires ``process`` scope.
   * - ``retry_items``
     - Queue up to 100 selected items on one enabled server. Requires ``process`` scope and enabled theme updates.

Library queries use the persisted dashboard snapshot and return refresh timestamps and recorded server errors.
Use ``refresh_libraries`` to request new metadata. Searches return library memberships, so an item in several
libraries can appear more than once; coverage counts each item once per server. Library filters require a server ID.
Server lists, library lists, and searches support ``limit`` and ``offset``, with a maximum page size of 200.
Follow ``next_offset`` until it is null.

``check_themerrdb`` accepts ``media_type`` (``movie``, ``show``, or ``collection``), ``database_id`` as a string,
and ``database`` (``themoviedb`` by default, or ``imdb`` for movies). Use the external IDs returned by
``search_items`` or provide an ID directly; a saved media server is not required. The result includes ``exists``
and the index's UTC ``last_refresh`` timestamp. The tool refreshes Themerr's shared index when it is older than
one hour. An unavailable index returns a tool error instead of claiming that the item is absent. A successful
lookup confirms database membership; it does not verify that the theme is installed or that its video is available.

Theme inspection reports observed state and upload metadata. It does not perform a processing scan or establish
every reason an item was skipped. Retry requests validate the entire selection before queuing anything, reject
ignored libraries, and deduplicate items already queued or active. Existing eligibility, ownership, and overwrite
settings still apply during processing; retrying can replace a theme when those settings permit it.

A finished dashboard refresh or scan job does not mean queued uploads have finished. Check ``queued_items``,
``active_items``, and ``uploads_idle`` from ``get_activity`` separately.

For logs, omit ``cursor`` to read recent file history, or use ``cursor=0`` to start current-session history.
Follow the returned cursor while ``has_more`` is true. Severity and message filters apply to each bounded batch;
an empty filtered page can still have more history. Session history resets when Themerr restarts.

Example requests
----------------

* "Show movies with failed themes on my Jellyfin server."
* "What percentage of my Movies library has theme music?"
* "Inspect this item's metadata and last theme upload."
* "Check whether movie TMDB ID 123 is in ThemerrDB."
* "Show recent YouTube extraction errors."
* "Refresh library metadata, then retry these three items."
