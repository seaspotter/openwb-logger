"""Infra-level configuration: how to reach the database (and, for the
self-update feature, where the repo checkout lives), read once from
environment variables at import time.

Everything about the tool's own behavior -- where openWB is, which logs to
collect, retention, poll interval -- is deliberately NOT here. It lives in
runtime_settings.py, stored in the database and edited from the web UI's
settings panel, with hardcoded (not env-derived) defaults on first boot.
That split matters for bundling this app together with its database into
a single image later: at that point even DATABASE_URL collapses to a fixed
localhost value, and there's nothing left to configure before first start.

The bind port (PORT) isn't here either: it's only ever needed by uvicorn's
own `--port` flag, handed to it directly by the container entrypoint (see
Dockerfile) -- there's no reason for application code to also know it.
"""
from __future__ import annotations

import os


class Settings:
    # postgresql://user:password@host:5432/dbname
    database_url: str = os.environ.get(
        "DATABASE_URL", "postgresql://openwb_logger:openwb_logger@localhost:5432/openwb_logger"
    )

    # Where the repo checkout is bind-mounted *inside this container* -- used
    # by app/updater.py to run `git pull`. Not the same as HOST_REPO_DIR.
    repo_dir: str = os.environ.get("REPO_DIR", "/repo")

    # Absolute path to the same checkout *on the Docker host*. Required
    # because self-update launches a sibling container over the mounted
    # docker socket (docker-outside-of-docker) -- volume paths for that
    # sibling are resolved by the host daemon, so a path meaningful only
    # inside this container (REPO_DIR) won't work for it. Self-update is
    # disabled (not just failing) when this isn't set, since a wrong value
    # would silently point the rebuild at the wrong directory.
    host_repo_dir: str | None = os.environ.get("HOST_REPO_DIR")


settings = Settings()
