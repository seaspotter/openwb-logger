# Only used to grab a static `docker` CLI binary (with the `compose` plugin
# bundled) for the self-update feature -- see app/updater.py. Never run
# itself; multi-stage purely to avoid an apt/network dependency at runtime.
FROM docker:27-cli AS dockercli

FROM python:3.12-slim

WORKDIR /app

# git: needed by app/updater.py's `git pull` against the bind-mounted repo
# checkout (REPO_DIR, only present when self-update is enabled). docker
# CLI: needed to launch the sibling container that performs the actual
# rebuild+recreate (see app/updater.py docstring for why that can't happen
# in this process). Harmless to have installed even when self-update isn't
# configured for this deployment.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

RUN useradd --create-home appuser
# The bind-mounted repo checkout (REPO_DIR) is owned by whatever UID/GID it
# has on the Docker host, which won't generally match appuser -- git
# refuses to operate on a directory it doesn't recognize as owned without
# this. A no-op when self-update isn't in use.
RUN git config --system --add safe.directory /repo

EXPOSE 8080

# Stays as root here on purpose: the entrypoint fixes up docker.sock group
# access (only relevant when self-update is enabled) before dropping to
# appuser itself -- see docker-entrypoint.sh.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
