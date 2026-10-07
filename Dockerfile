# syntax=docker/dockerfile:1
FROM --platform=$BUILDPLATFORM mcr.microsoft.com/dotnet/sdk:11.0 AS connector
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
WORKDIR /connector
COPY connectors/jellyfin/ connectors/jellyfin/
COPY connectors/Directory.Build.props connectors/Directory.Build.props
COPY .editorconfig .editorconfig
COPY scripts/build_connector.py scripts/build_connector.py
COPY src/jellyfin/compatibility.py src/jellyfin/compatibility.props src/jellyfin/
COPY src/common/version.py src/common/version.py
ARG BUILD_VERSION
ARG THEMERR_VERSION=${BUILD_VERSION}
RUN uv run --no-project --python 3.14 scripts/build_connector.py

FROM ghcr.io/astral-sh/uv:0.12-python3.14-trixie-slim AS base

COPY --from=denoland/deno:bin-2.9.7 /deno /usr/local/bin/deno

FROM base AS build

# install build dependencies
RUN <<EOF
set -eu
apt-get update -y
apt-get install -y --no-install-recommends \
    build-essential \
    libjpeg-dev \
    libopenblas-dev \
    npm \
    pkg-config \
    zlib1g-dev
apt-get clean
rm -rf /var/lib/apt/lists/*
EOF

# uv creates the environment at a stable path for the runtime stage.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# setup app directory
WORKDIR /build
COPY . .
COPY --from=connector /connector/jellyfin-connector/ /build/jellyfin-connector/
COPY --from=connector /connector/src/common/version.py /build/src/common/version.py

# setup locked Python dependencies
RUN uv sync --locked --no-build --no-install-project --no-python-downloads --python /usr/local/bin/python

# setup npm and dependencies
RUN npm ci --ignore-scripts && npm run build

FROM base AS app

# copy runtime files from builder
COPY --from=build /build/src/ /app/src/
COPY --from=build /build/web/ /app/web/
COPY --from=build /build/locale/ /app/locale/
COPY --from=build /build/LICENSE /app/LICENSE
COPY --from=build /build/jellyfin-connector/ /app/jellyfin-connector/

# copy python venv
COPY --from=build /opt/venv/ /opt/venv/
# use the venv
ENV PATH="/opt/venv/bin:$PATH"
# site-packages are in /opt/venv/lib/python<version>/site-packages/

# setup remaining env variables
ENV THEMERR_DOCKER=True

# network setup
EXPOSE 9494
EXPOSE 9495

# setup user
ARG PGID=1000
ENV PGID=${PGID}
ARG PUID=1000
ENV PUID=${PUID}
ENV TZ="UTC"
ARG UNAME=lizard
ENV UNAME=${UNAME}

ENV HOME=/home/$UNAME

# setup user
RUN <<EOF
set -eu
groupadd -f -g "${PGID}" "${UNAME}"
useradd -lm -d "${HOME}" -s /bin/bash -g "${PGID}" -u "${PUID}" "${UNAME}"
mkdir -p "${HOME}/.config/themerr"
ln -s "${HOME}/.config/themerr" /config
chown -R "${UNAME}" "${HOME}"
EOF

# mounts
VOLUME /config

USER ${UNAME}
WORKDIR ${HOME}

ENTRYPOINT ["python", "/app/src/main.py"]
HEALTHCHECK --start-period=90s CMD ["python", "/app/src/main.py", "--docker_healthcheck"]
