### lizardbyte/themerr-plex

This is a [docker-mod](https://linuxserver.github.io/docker-mods/) for
[plex](https://hub.docker.com/r/linuxserver/plex) which adds [Themerr-plex](https://github.com/LizardByte/Themerr-plex)
to plex as a plugin, to be downloaded/updated during container start.

This image extends the plex image, and is not intended to be created as a separate container.

### Installation

In plex docker arguments, set an environment variable `DOCKER_MODS=lizardbyte/themerr-plex:latest` or
`DOCKER_MODS=ghcr.io/lizardbyte/themerr-plex:latest`

If adding multiple mods, enter them in an array separated by `|`, such as
`DOCKER_MODS=lizardbyte/themerr-plex:latest|linuxserver/mods:other-plex-mod`

### Supported Architectures

Specifying `lizardbyte/themerr-plex:latest` or `ghcr.io/lizardbyte/themerr-plex:latest` should retrieve the correct
image for your architecture.

The architectures supported by this image are:

| Architecture | Available |
|:------------:|:---------:|
|    x86-64    |     ✅     |
|    arm64     |     ✅     |
|    armhf     |     ✅     |
