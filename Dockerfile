# syntax=docker/dockerfile:1.4
# artifacts: false
# platforms: linux/amd64,linux/arm64/v8,linux/arm/v7
FROM python:2.7-buster AS buildstage
# in order to use ubuntu:22.04 or newer, we will need to install git from source

# build args
ARG BUILD_VERSION
ARG COMMIT
ARG GITHUB_SHA=$COMMIT
# note: BUILD_VERSION may be blank, COMMIT is also available
# note: build_plist.py uses BUILD_VERSION and GITHUB_SHA

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
# git 2.34 does not work with python 2.7
# git 2.25 may work since it is included with ubuntu 20.04
# too install git from source, see here: https://stackoverflow.com/a/52344030/11214013
# install dependencies
#RUN <<_DEPS
##!/bin/bash
#set -e
#apt-get update -y
#apt-get install -y --no-install-recommends \
#  git=1:2.34.1* \
#  python2=2.7.18* \
#  python-pip=20.3.4*
#apt-get clean
#rm -rf /var/lib/apt/lists/*
#_DEPS

# create build dir and copy GitHub repo there
COPY --link . /build

# set build dir
WORKDIR /build

# update pip
RUN <<_PIP
#!/bin/bash
set -e
python -m pip --no-python-version-warning --disable-pip-version-check install --no-cache-dir --upgrade \
  pip setuptools requests
# requests required to install python-plexapi
# dev requirements not necessary for docker image, significantly speeds up build since lxml doesn't need to build
_PIP

# build plugin
RUN <<_BUILD
#!/bin/bash
set -e
python -m pip --no-python-version-warning --disable-pip-version-check install --no-cache-dir --upgrade \
  --target=./Contents/Libraries/Shared -r requirements.txt --no-warn-script-location
python ./scripts/build_plist.py
_BUILD

# clean
RUN <<_CLEAN
#!/bin/bash
set -e
rm -rf ./scripts/
# list contents
ls -a
_CLEAN

FROM scratch AS deploy

# variables
ARG PLUGIN_NAME="Themerr-plex.bundle"
ARG PLUGIN_DIR="/config/Library/Application Support/Plex Media Server/Plug-ins"

# add files from buildstage
# trailing slash on build directory copies the contents of the directory, instead of the directory itself
COPY --link --from=buildstage /build/ $PLUGIN_DIR/$PLUGIN_NAME
