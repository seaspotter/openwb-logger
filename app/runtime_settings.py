"""User-editable settings: where openWB is, which of its logs to collect,
how long to keep them, and how often to poll. Stored in the `app_settings`
table (one JSONB row) so changes made through the web UI take effect on the
next poll cycle without a container restart -- unlike app/config.py, which
holds deployment-level settings (DB connection, port, ...) fixed for the
life of the process.
"""
from __future__ import annotations

from typing import TypedDict

from .config import settings as env_settings
from .db import get_kv, set_kv
from .log_catalog import CATALOG, DEFAULT_ENABLED

_TABLE = "app_settings"
_KEY = "config"

MIN_FETCH_INTERVAL_SECONDS = 60
MAX_FETCH_INTERVAL_SECONDS = 86400
MIN_RETENTION_DAYS = 1
MAX_RETENTION_DAYS = 3650


class RuntimeSettings(TypedDict):
    openwb_base_url: str
    openwb_ramdisk_path: str
    enabled_sources: list[str]
    fetch_interval_seconds: int
    retention_days: int


def defaults() -> RuntimeSettings:
    return {
        "openwb_base_url": env_settings.openwb_base_url,
        "openwb_ramdisk_path": env_settings.openwb_ramdisk_path,
        "enabled_sources": list(DEFAULT_ENABLED),
        "fetch_interval_seconds": env_settings.fetch_interval_seconds,
        "retention_days": env_settings.retention_days,
    }


class ValidationError(ValueError):
    pass


def validate(patch: dict) -> dict:
    """Validates and normalizes a settings patch. Raises ValidationError
    with a human-readable message on the first problem found."""
    clean: dict = {}

    if "openwb_base_url" in patch:
        url = str(patch["openwb_base_url"]).strip().rstrip("/")
        if not url.startswith(("http://", "https://")):
            raise ValidationError("openwb_base_url must start with http:// or https://")
        clean["openwb_base_url"] = url

    if "openwb_ramdisk_path" in patch:
        path = str(patch["openwb_ramdisk_path"]).strip()
        if not path.startswith("/"):
            raise ValidationError("openwb_ramdisk_path must start with /")
        clean["openwb_ramdisk_path"] = path.rstrip("/")

    if "enabled_sources" in patch:
        sources = patch["enabled_sources"]
        if not isinstance(sources, list) or not sources:
            raise ValidationError("enabled_sources must be a non-empty list")
        unknown = [s for s in sources if s not in CATALOG]
        if unknown:
            raise ValidationError(f"unknown log source(s): {', '.join(unknown)}")
        clean["enabled_sources"] = sources

    if "fetch_interval_seconds" in patch:
        interval = int(patch["fetch_interval_seconds"])
        if not (MIN_FETCH_INTERVAL_SECONDS <= interval <= MAX_FETCH_INTERVAL_SECONDS):
            raise ValidationError(
                f"fetch_interval_seconds must be between {MIN_FETCH_INTERVAL_SECONDS} "
                f"and {MAX_FETCH_INTERVAL_SECONDS}"
            )
        clean["fetch_interval_seconds"] = interval

    if "retention_days" in patch:
        days = int(patch["retention_days"])
        if not (MIN_RETENTION_DAYS <= days <= MAX_RETENTION_DAYS):
            raise ValidationError(
                f"retention_days must be between {MIN_RETENTION_DAYS} and {MAX_RETENTION_DAYS}"
            )
        clean["retention_days"] = days

    return clean


async def get_settings(pool) -> RuntimeSettings:
    stored = await get_kv(pool, _TABLE, _KEY, default=None)
    if stored is None:
        seeded = defaults()
        await set_kv(pool, _TABLE, _KEY, seeded)
        return seeded
    # Merge over defaults so new keys introduced later are forward-compatible
    # with settings rows written by an older version.
    return {**defaults(), **stored}


async def update_settings(pool, patch: dict) -> RuntimeSettings:
    clean = validate(patch)
    current = await get_settings(pool)
    current.update(clean)
    await set_kv(pool, _TABLE, _KEY, current)
    return current
