FROM python:3.12-slim

WORKDIR /app

# git: needed by app/updater.py's `git pull` against the repo checkout that
# docker-compose.yml bind-mounts onto this same WORKDIR for self-update.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Runs as root: the bind-mounted repo checkout (see docker-compose.yml) is
# owned by whatever UID/GID it has on the Docker host, and self-update's
# `git pull` needs to write to it. No Docker socket is involved anywhere in
# this image, unlike an earlier version of self-update -- see
# app/updater.py and DEPLOYMENT.md for what this container can and can't do.

EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
