Jellyfin Connector
==================

The connector provides administrator-only endpoints for theme ownership, upload, and verified imports
from the older Themerr-jellyfin plugin. Themerr manages discovery, downloads, and scheduling.
The reference below is generated from the connector's C# XML documentation comments.

Plugin and endpoints
--------------------

.. doxygenclass:: Themerr::Connector::Plugin
   :members:

.. doxygenclass:: Themerr::Connector::Controller
   :members:

Themes and ownership
--------------------

.. doxygenclass:: Themerr::Connector::ThemeFiles
   :members:

.. doxygenclass:: Themerr::Connector::ThemeState
   :members:

.. doxygenclass:: Themerr::Connector::ThemeConflictException
   :members:

.. doxygenclass:: Themerr::Connector::ThemeOwnership
   :members:

.. doxygenclass:: Themerr::Connector::Ownership
   :members:

.. doxygenclass:: Themerr::Connector::OwnershipEntry
   :members:

Database and migrations
-----------------------

.. doxygenclass:: Themerr::Connector::OwnershipContext
   :members:
   :protected-members:

.. doxygenclass:: Themerr::Connector::InitialOwnership
   :members:
   :protected-members:

.. doxygenclass:: Themerr::Connector::OwnershipModelSnapshot
   :members:
   :protected-members:

Legacy ownership imports
------------------------

.. doxygenclass:: Themerr::Connector::LegacyOwnership
   :members:

.. doxygenclass:: Themerr::Connector::LegacyOwnershipContext
   :members:
   :protected-members:

.. doxygenclass:: Themerr::Connector::LegacyTheme
   :members:
