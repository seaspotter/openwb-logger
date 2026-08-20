"""Infra-level configuration: how to reach the database, read once from an
environment variable at import time.

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


settings = Settings()
