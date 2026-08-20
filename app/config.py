"""Central configuration, read once from environment variables."""
from __future__ import annotations

import os


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return int(raw)


class Settings:
    # Base URL of the openWB web server, e.g. http://10.1.5.32
    openwb_base_url: str = os.environ.get("OPENWB_BASE_URL", "http://openwb").rstrip("/")

    # Path (below the base URL) to the live main log on the ramdisk.
    openwb_log_path: str = os.environ.get("OPENWB_LOG_PATH", "/openWB/ramdisk/main.log")

    # openWB rotates main.log -> main.log.1 .. main.log.<N> at 5MB each.
    # Used as a fallback source when a rotation happens between two polls.
    backup_count: int = _int_env("OPENWB_BACKUP_COUNT", 4)

    # How often to poll the live log.
    fetch_interval_seconds: int = _int_env("FETCH_INTERVAL_SECONDS", 600)  # 10 min

    # HTTP timeout per request.
    http_timeout_seconds: int = _int_env("HTTP_TIMEOUT_SECONDS", 15)

    # How many days of log lines to keep. Enforced by a TimescaleDB retention
    # policy, not application code.
    retention_days: int = _int_env("RETENTION_DAYS", 30)

    # Number of trailing raw lines kept (in the DB) to detect overlap/rotation
    # between polls.
    tail_window: int = _int_env("TAIL_WINDOW", 50)

    # postgresql://user:password@host:5432/dbname
    database_url: str = os.environ.get(
        "DATABASE_URL", "postgresql://openwb_logger:openwb_logger@localhost:5432/openwb_logger"
    )

    # Web UI / API bind port.
    port: int = _int_env("PORT", 8080)

    @property
    def log_url(self) -> str:
        return f"{self.openwb_base_url}{self.openwb_log_path}"

    def backup_url(self, n: int) -> str:
        return f"{self.openwb_base_url}{self.openwb_log_path}.{n}"


settings = Settings()
