#!/bin/sh
# Runs as root so it *can* fix up docker.sock group access when self-update
# is enabled (docker.sock is bind-mounted -- see docker-compose.selfupdate.yml),
# then always drops to the unprivileged appuser to actually run the app.
# Deployments that don't use self-update never get docker.sock mounted, so
# this is a no-op there and appuser stays exactly as unprivileged as before.
set -e

if [ -S /var/run/docker.sock ]; then
  DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)
  getent group "$DOCKER_GID" >/dev/null 2>&1 || groupadd -g "$DOCKER_GID" dockerhost
  usermod -aG "$DOCKER_GID" appuser
fi

exec su appuser -s /bin/sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"
