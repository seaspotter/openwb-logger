"""User-editable settings: where openWB is, which of its logs to collect,
how long to keep them, how often to poll, and how many lines to show per
page in the UI. Stored in the `app_settings`
table (one JSONB row) so changes made through the web UI take effect on the
next poll cycle without a container restart -- unlike app/config.py, which
holds infra-level settings (DB connection, port, ...) fixed for the life
of the process.

Deliberately no environment variables here: this is the tool's own
configuration, meant to be set up once through the UI after first start,
not wired up at deploy time. That keeps things simple for bundling the app
together with its database into a single image later on.
"""
from __future__ import annotations

from typing import TypedDict

from .db import get_kv, set_kv
from .log_catalog import CATALOG, DEFAULT_ENABLED

_TABLE = "app_settings"
_KEY = "config"

# openWB devices commonly answer to this hostname via mDNS/avahi out of the
# box, so it's a reasonable guess -- but still just a starting point the
# user is expected to confirm/correct in the settings panel.
DEFAULT_OPENWB_BASE_URL = "http://openwb"
DEFAULT_OPENWB_RAMDISK_PATH = "/openWB/ramdisk"
DEFAULT_FETCH_INTERVAL_SECONDS = 600  # 10 min
DEFAULT_RETENTION_DAYS = 30
DEFAULT_PAGE_SIZE = 5000
# openWB's own pastebin, https://github.com/lucko/paste self-hosted --
# verified against the live instance: the frontend at paste.openwb.de
# serves a React app whose compiled JS points its uploads at bytebin.
# openwb.de/post (bytebin is paste's storage backend), and the resulting
# key is viewable at paste.openwb.de/<key>. Configurable in case that ever
# changes or someone points this at their own instance.
DEFAULT_PASTE_UPLOAD_URL = "https://bytebin.openwb.de/post"
DEFAULT_PASTE_VIEW_URL = "https://paste.openwb.de/"

MIN_FETCH_INTERVAL_SECONDS = 60
MAX_FETCH_INTERVAL_SECONDS = 86400
MIN_RETENTION_DAYS = 1
MAX_RETENTION_DAYS = 3650
MIN_PAGE_SIZE = 100
# Matches /api/logs' own `limit` cap (app/web.py) -- no point accepting a
# setting the API would reject anyway.
MAX_PAGE_SIZE = 20000


class RuntimeSettings(TypedDict):
    openwb_base_url: str
    openwb_ramdisk_path: str
    enabled_sources: list[str]
    fetch_interval_seconds: int
    retention_days: int
    page_size: int
    paste_upload_url: str
    paste_view_url: str


def defaults() -> RuntimeSettings:
    return {
        "openwb_base_url": DEFAULT_OPENWB_BASE_URL,
        "openwb_ramdisk_path": DEFAULT_OPENWB_RAMDISK_PATH,
        "enabled_sources": list(DEFAULT_ENABLED),
        "fetch_interval_seconds": DEFAULT_FETCH_INTERVAL_SECONDS,
        "retention_days": DEFAULT_RETENTION_DAYS,
        "page_size": DEFAULT_PAGE_SIZE,
        "paste_upload_url": DEFAULT_PASTE_UPLOAD_URL,
        "paste_view_url": DEFAULT_PASTE_VIEW_URL,
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
            raise ValidationError("Die openWB-Adresse muss mit http:// oder https:// beginnen")
        clean["openwb_base_url"] = url

    if "openwb_ramdisk_path" in patch:
        path = str(patch["openwb_ramdisk_path"]).strip()
        if not path.startswith("/"):
            raise ValidationError("Der Ramdisk-Pfad muss mit / beginnen")
        clean["openwb_ramdisk_path"] = path.rstrip("/")

    if "enabled_sources" in patch:
        sources = patch["enabled_sources"]
        if not isinstance(sources, list) or not sources:
            raise ValidationError("Mindestens ein Log muss ausgewählt sein")
        unknown = [s for s in sources if s not in CATALOG]
        if unknown:
            raise ValidationError(f"Unbekannte Log-Quelle(n): {', '.join(unknown)}")
        clean["enabled_sources"] = sources

    if "fetch_interval_seconds" in patch:
        interval = int(patch["fetch_interval_seconds"])
        if not (MIN_FETCH_INTERVAL_SECONDS <= interval <= MAX_FETCH_INTERVAL_SECONDS):
            raise ValidationError(
                f"Das Abrufintervall muss zwischen {MIN_FETCH_INTERVAL_SECONDS} "
                f"und {MAX_FETCH_INTERVAL_SECONDS} Sekunden liegen"
            )
        clean["fetch_interval_seconds"] = interval

    if "retention_days" in patch:
        days = int(patch["retention_days"])
        if not (MIN_RETENTION_DAYS <= days <= MAX_RETENTION_DAYS):
            raise ValidationError(
                f"Die Aufbewahrungsdauer muss zwischen {MIN_RETENTION_DAYS} "
                f"und {MAX_RETENTION_DAYS} Tagen liegen"
            )
        clean["retention_days"] = days

    if "page_size" in patch:
        size = int(patch["page_size"])
        if not (MIN_PAGE_SIZE <= size <= MAX_PAGE_SIZE):
            raise ValidationError(
                f"Die Seitengröße muss zwischen {MIN_PAGE_SIZE} und {MAX_PAGE_SIZE} liegen"
            )
        clean["page_size"] = size

    if "paste_upload_url" in patch:
        url = str(patch["paste_upload_url"]).strip()
        if not url.startswith(("http://", "https://")):
            raise ValidationError("Die Paste-Upload-URL muss mit http:// oder https:// beginnen")
        clean["paste_upload_url"] = url

    if "paste_view_url" in patch:
        url = str(patch["paste_view_url"]).strip()
        if not url.startswith(("http://", "https://")):
            raise ValidationError("Die Paste-Anzeige-URL muss mit http:// oder https:// beginnen")
        clean["paste_view_url"] = url if url.endswith("/") else url + "/"

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
