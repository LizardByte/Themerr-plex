:github_url: https://github.com/LizardByte/Themerr-plex/tree/nightly/docs/source/about/installation.rst

Installation
============
The recommended method for running Themerr-plex is to use the `bundle`_ in the `latest release`_.

Bundle
------
The bundle is cross platform, meaning Linux, macOS, and Windows are supported.

#. Download the ``themerr-plex.bundle.zip`` from the `latest release`_
#. Extract the contents to your Plex Media Server Plugins directory.

.. Tip:: See
   `How do I find the Plug-Ins folder <https://support.plex.tv/articles/201106098-how-do-i-find-the-plug-ins-folder>`__
   for information specific to your Plex server install.

Docker
------
Docker images are available on `Dockerhub`_ and `ghcr.io`_.

See :ref:`Docker <about/docker:docker>` for additional information.

Source
------
.. Caution:: Installing from source is not recommended most users.

#. Follow the steps in :ref:`Build <contributing/build:build>`.
#. Move the compiled ``themerr-plex.bundle`` to your Plex Media Server Plugins directory.

.. _latest release: https://github.com/LizardByte/Themerr-plex/releases/latest
.. _Dockerhub: https://hub.docker.com/repository/docker/lizardbyte/themerr-plex
.. _ghcr.io: https://github.com/orgs/LizardByte/packages?repo_name=themerr-plex
