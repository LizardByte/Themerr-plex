# artifacts: false
# platforms: linux/amd64,linux/arm64/v8
FROM ghcr.io/astral-sh/uv:0.12.21-python3.14-trixie-slim AS base

COPY --from=denoland/deno:bin-2.9.7 /deno /usr/local/bin/deno

FROM base AS build

# install build dependencies
RUN apt-get update -y \
    && apt-get install -y --no-install-recommends \
       build-essential libjpeg-dev npm pkg-config libopenblas-dev zlib1g-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# uv creates the environment at a stable path for the runtime stage.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# setup app directory
WORKDIR /build
COPY . .

# setup locked Python dependencies
RUN uv sync --locked --extra docs --no-install-project --no-python-downloads

# compile locales
RUN python scripts/_locale.py --compile

# setup npm and dependencies
RUN npm ci --ignore-scripts && npm run build

# build bundled documentation with Dockle
RUN python -m dockle check && python -m dockle build

FROM base AS app

# copy runtime files from builder
COPY --from=build /build/src/ /app/src/
COPY --from=build /build/web/ /app/web/
COPY --from=build /build/locale/ /app/locale/
COPY --from=build /build/_site/ /app/_site/
COPY --from=build /build/scripts/_locale.py /app/scripts/_locale.py
COPY --from=build /build/LICENSE /app/LICENSE

# copy python venv
COPY --from=build /opt/venv/ /opt/venv/
# use the venv
ENV PATH="/opt/venv/bin:$PATH"
# site-packages are in /opt/venv/lib/python<version>/site-packages/

# setup remaining env variables
ENV THEMERR_DOCKER=True

# network setup
EXPOSE 9494

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
RUN groupadd -f -g "${PGID}" "${UNAME}" \
    && useradd -lm -d "${HOME}" -s /bin/bash -g "${PGID}" -u "${PUID}" "${UNAME}" \
    && mkdir -p "${HOME}/.config/themerr-plex" \
    && ln -s "${HOME}/.config/themerr-plex" /config \
    && chown -R "${UNAME}" "${HOME}"

# mounts
VOLUME /config

USER ${UNAME}
WORKDIR ${HOME}

ENTRYPOINT ["python", "/app/src/themerr_plex.py"]
HEALTHCHECK --start-period=90s CMD ["python", "/app/src/themerr_plex.py", "--docker_healthcheck"]
