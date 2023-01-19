# platforms: linux/amd64,linux/arm64/v8,linux/arm/v7
# artifacts: false
FROM python:2.7.18-buster AS buildstage

# build args
ARG BUILD_VERSION
ARG COMMIT
ARG GITHUB_SHA=$COMMIT
# note: BUILD_VERSION may be blank, COMMIT is also available
# note: build_plist.py uses BUILD_VERSION and GITHUB_SHA

# create build dir and copy GitHub repo there
COPY --link . /build

# set build dir
WORKDIR /build

# update pip
RUN <<_PIP
#!/bin/bash
python -m pip --no-python-version-warning --disable-pip-version-check install --no-cache-dir --upgrade \
  pip==20.3.4 setuptools requests
# requests required to install python-plexapi
# dev requirements not necessary for docker image, significantly speeds up build since lxml doesn't need to build
_PIP

# build plugin
RUN <<_BUILD
#!/bin/bash
python ./scripts/install_requirements.py
python ./scripts/build_plist.py
_BUILD

# clean
RUN <<_CLEAN
#!/bin/bash
rm -rf ./scripts/
# list contents
ls -a
_CLEAN

FROM scratch AS deploy

# variables
ARG PLUGIN_NAME="Themerr-plex.bundle"
ARG PLUGIN_DIR="/config/Library/Application Support/Plex Media Server/Plug-ins"

# add files from buildstage
COPY --link --from=buildstage /build/ $PLUGIN_DIR/$PLUGIN_NAME
