FROM python:3.12-slim

WORKDIR /app

# git: needed by app/updater.py's `git pull` against the repo checkout that
# docker-compose.yml bind-mounts onto this same WORKDIR for self-update.
# tzdata: without it, setting TZ (see docker-compose.yml) has nothing to
# resolve against, and datetime.now() (fetcher.py's last_fetch_at etc.)
# stays on the container's default UTC regardless of TZ.
RUN apt-get update && apt-get install -y --no-install-recommends git tzdata \
    && rm -rf /var/lib/apt/lists/*

# All our dependencies (asyncpg, cffi via cryptography, ...) have prebuilt
# wheels for amd64 and arm64 -- the two platforms this image targets (see
# .github/workflows/docker-publish.yml) -- so no compiler/build stage is
# needed here, unlike when arm/v7 was in the mix.
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
ENV PATH=/root/.local/bin:$PATH

COPY app ./app

# The bind-mounted repo checkout (see docker-compose.yml) is owned by
# whatever UID/GID it has on the Docker host, not root (which this
# container runs as) -- without this, git refuses every command against
# it ("detected dubious ownership in repository at '/app'"), which is
# exactly why the version display was silently showing "unknown" instead
# of a real git describe.
RUN git config --system --add safe.directory /app

# Baked-in fallback for the settings panel's version display (GET
# /api/update/version) when there's no live git checkout at /app to read a
# commit from -- e.g. a plain `docker run`/registry-image deployment
# without docker-compose.yml's repo bind-mount. Set from CI, see
# .github/workflows/docker-publish.yml.
ARG VERSION=unknown
ENV OPENWB_LOGGER_IMAGE_VERSION=$VERSION

# Runs as root: the bind-mounted repo checkout (see docker-compose.yml) is
# owned by whatever UID/GID it has on the Docker host, and self-update's
# `git pull` needs to write to it. No Docker socket is involved anywhere in
# this image, unlike an earlier version of self-update -- see
# app/updater.py and DEPLOYMENT.md for what this container can and can't do.

EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
