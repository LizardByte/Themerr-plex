# buildstage
FROM python:2.7.18-alpine3.11 as buildstage

# build args
ARG BUILD_VERSION
ARG COMMIT
ARG GITHUB_SHA=$COMMIT
# note: BUILD_VERSION may be blank, COMMIT is also available
# note: build_plist.py uses BUILD_VERSION and GITHUB_SHA

# setup build directory
RUN mkdir /build
WORKDIR /build/

# copy repo
COPY . .

RUN python  # update pip \
      -m pip --no-python-version-warning --disable-pip-version-check install --upgrade pip==20.3.4 setuptools \
    && python -m pip install --upgrade -r requirements-dev.txt  # install dev requirements \
    && python ./scripts/install_requirements.py  # install plugin requirements \
    && python ./scripts/build_plist.py  # build plist \
    && rm -r ./scripts/  # remove scripts dir

# single layer deployed image
FROM scratch

# variables
ARG PLUGIN_NAME="Themerr-plex.bundle"
ARG PLUGIN_DIR="/config/Library/Application Support/Plex Media Server/Plug-ins"

# add files from buildstage
COPY --from=buildstage /build/ $PLUGIN_DIR/$PLUGIN_NAME
