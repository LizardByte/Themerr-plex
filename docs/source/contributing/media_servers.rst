Media-server integration boundary
=================================

Plex and Jellyfin implementations live in ``src/plex`` and ``src/jellyfin``.
Shared services use the abstract contracts in ``src/media_servers/base.py``;
``media_servers.get_backend()`` returns a registry that routes saved server IDs
to their implementation. Jellyfin IDs have a ``jellyfin:`` prefix. Existing Plex
IDs and the default Plex connection retain their original meaning.

``MediaServerBackend`` owns saved connections, public connection settings,
account authorization status, event-listener lifecycle, and integration-specific
web routes. ``MediaServer`` owns operations on one server: library discovery,
dashboard snapshots, scanning, item updates, artwork, selected-theme streams,
browser links, and an optional TMDB metadata service. Implementations retain the
server identity and use ``storage.server_scope`` around storage and native work.

The Plex package owns SDK objects, agent and GUID interpretation, upload methods,
metadata-directory cleanup, account sign-in, discovery, and TMDB proxy credentials.
The Jellyfin package owns REST requests, pagination, UUID validation, provider
metadata, API-key connections, and connector installation and verification.
Credentials use the shared secure store with independent account and server
namespaces. Public records never include tokens or API keys. Stream consumers must close
upstream responses on rejection, HEAD requests, disconnects, and completion;
credentials and upstream response bodies must never enter public failures.

``media_servers.processing`` owns the worker queue and scheduled scan loop. Queue
entries contain a server ID and an opaque string item ID. Duplicate queued and
active work is suppressed within a server, while identical IDs on different
servers remain independent. Paused or removed servers are skipped by workers.
Failed work releases its active entry so a later scan can retry it. Plex also
listens for library events; Jellyfin uses the shared scheduled scans.

``themerr.cache`` owns refresh orchestration and successful-refresh notifications.
An unavailable server keeps its last dashboard snapshot and does not interrupt
other servers. Each implementation publishes the existing section and item
dictionary format through ``storage.replace_dashboard`` only after a complete
scan, using the dashboard revision to preserve concurrent successful uploads.

The database migration changes library keys to strings while retaining existing
Plex records. Server-scoped playback routes accept opaque item IDs; legacy integer
Plex playback routes remain available. Existing Plex configuration keys and
credential-store namespaces remain compatible.

Jellyfin connector
------------------

The small connector under ``connectors/jellyfin`` supplies administrator-only
identity, theme-state, and upload endpoints. It has no download service, scheduled
task, or settings UI. Themerr resolves metadata and downloads audio through the
shared Python services. AAC remains in MP4; WebM Opus is remuxed to Ogg without
re-encoding.

``scripts/build_connector.py`` builds one assembly for each explicitly supported
Jellyfin ABI: 10.11 and 12.1. Its descriptor records a fingerprint of the connector
source, build profiles, and Themerr version. Installation selects the exact
bundled version for the target server, and uploads require a matching fingerprint,
protocol, and ABI. Unsupported versions and stale connectors fail with an
installation error. Jellyfin must restart to load a newly installed plugin.

Themerr serves the manifest and two archives at fixed routes under
``/jellyfin/connector``. These exact GET and HEAD routes are public so Jellyfin
can download them. Connection and installation APIs require the usual admin
session and CSRF token. Downloads use the shared canonical path policy and file
response helper. Request values never select filenames. The manifest uses the
administrator-selected Themerr address, rather than the request's Host header.
Installing the connector preserves the server's other plugin repositories.

The connector maps native item GUIDs through Jellyfin's library manager to local
movie, series, and collection folders. Uploads use fixed ``theme.m4a`` or
``theme.opus`` filenames. A digest-verified ownership record permits subsequent
updates; existing user themes and manually changed files are preserved. An
upload is bounded, verified, and staged before replacing an owned file. File
links are rejected. Python records successful uploads only after the connector
acknowledges the expected digest.

Tests under ``tests/unit/plex`` and ``tests/unit/jellyfin`` mock native services.
``tests/unit/media_servers`` covers shared orchestration. Functional Jellyfin
tests cover authentication, CSRF, fixed resource routes, and rejected paths.
The C# harness under ``connectors/jellyfin.tests`` checks native file ownership,
integrity, replacement, and link protection.
