"""Deployment-level configuration: fixed for the life of the process, read
once from environment variables at import time.

These are the settings that only make sense to change by redeploying the
container (DB connection, port). Settings a user should be able to change
at runtime through the web UI -- where openWB is, which logs to collect,
retention, poll interval -- live in runtime_settings.py instead, backed by
the database; the values here only act as their *initial* defaults on first
boot.
"""
from __future__ import annotations

import os


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return int(raw)


class Settings:
    # Initial default for the runtime "openwb_base_url" setting.
    openwb_base_url: str = os.environ.get("OPENWB_BASE_URL", "http://openwb").rstrip("/")

    # Initial default for the runtime "openwb_ramdisk_path" setting.
    openwb_ramdisk_path: str = os.environ.get("OPENWB_RAMDISK_PATH", "/openWB/ramdisk")

    # Initial default for the runtime "fetch_interval_seconds" setting.
    fetch_interval_seconds: int = _int_env("FETCH_INTERVAL_SECONDS", 600)  # 10 min

    # Initial default for the runtime "retention_days" setting.
    retention_days: int = _int_env("RETENTION_DAYS", 30)

    # HTTP timeout per request. Not runtime-editable.
    http_timeout_seconds: int = _int_env("HTTP_TIMEOUT_SECONDS", 15)

    # Number of trailing raw lines kept (in the DB) per source to detect
    # overlap/rotation between polls. Not runtime-editable.
    tail_window: int = _int_env("TAIL_WINDOW", 50)

    # postgresql://user:password@host:5432/dbname
    database_url: str = os.environ.get(
        "DATABASE_URL", "postgresql://openwb_logger:openwb_logger@localhost:5432/openwb_logger"
    )

    # Web UI / API bind port.
    port: int = _int_env("PORT", 8080)


settings = Settings()
