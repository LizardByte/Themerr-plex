Media-server integration boundary
=================================

Plex is the only supported media server. Its implementation lives in ``src/plex``.
Shared services use the abstract contracts in ``src/media_servers/base.py``;
``media_servers.get_backend()`` selects the Plex implementation in one place.

``MediaServerBackend`` owns saved connections, public connection settings,
account authorization status, event-listener lifecycle, and integration-specific
web routes. ``MediaServer`` owns operations on one server: library discovery,
dashboard snapshots, scanning, item updates, artwork, selected-theme streams,
browser links, and an optional TMDB metadata service. Implementations retain the
server identity and use ``storage.server_scope`` around storage and native work.

The Plex package owns SDK objects, agent and GUID interpretation, upload methods
and verification, metadata-directory layout and cleanup, account sign-in,
discovery protocols, TMDB proxy credentials, and native media paths. Shared
callers receive public dictionaries or HTTP streams. Stream consumers must close
upstream responses on rejection, HEAD requests, disconnects, and completion;
credentials and upstream response bodies must never enter public failures.

``media_servers.processing`` owns the worker queue and scheduled scan loop. Queue
entries contain a server ID and an opaque string item ID. Duplicate queued and
active work is suppressed within a server, while identical IDs on different
servers remain independent. Paused or removed servers are skipped by workers.
Failed work releases its active entry so a later scan can retry it.

``themerr.cache`` owns refresh orchestration and successful-refresh notifications.
An unavailable server keeps its last dashboard snapshot and does not interrupt
other servers. Each implementation publishes the existing section and item
dictionary format through ``storage.replace_dashboard`` only after a complete
scan, using the dashboard revision to preserve concurrent successful uploads.

The existing database tables, ``rating_key`` fields, HTTP routes, configuration
keys, and credential-store namespaces remain compatible with Plex installations.
Dashboard storage still uses integer library keys, and the existing playback
routes accept integer rating keys. Changing those persisted fields and public
routes belongs to the later work that introduces another integration.
The current browser interface and onboarding still describe Plex. This refactor
does not introduce a server-type setting or another server implementation.

Tests under ``tests/unit/plex`` cover native integration behavior with mocked
services. Tests under ``tests/unit/media_servers`` cover the shared contracts
and orchestration with opaque identifiers, without a live media server.
