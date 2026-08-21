"""Static catalog of the logs openWB writes to its ramdisk.

Filenames, rotation depth, and format are fixed by openWB itself (see
openWB/core packages/helpermodules/logger.py) -- not something a user
would ever need to edit, so this is a plain constant rather than a DB
table. What IS user-editable (which of these are enabled) lives in
runtime_settings.py.
"""
from __future__ import annotations

from typing import Literal, TypedDict

LogFormat = Literal["detailed", "short"]


class LogSource(TypedDict):
    label: str
    format: LogFormat
    backup_count: int
    default_enabled: bool


# name -> metadata. `name` is also the filename stem: "<name>.log".
CATALOG: dict[str, LogSource] = {
    "main": {
        "label": "Main log",
        "format": "detailed",
        "backup_count": 4,
        "default_enabled": True,
    },
    "chargelog": {
        "label": "Charge log",
        "format": "short",
        "backup_count": 1,
        "default_enabled": False,
    },
    "mqtt": {
        "label": "MQTT log",
        "format": "short",
        "backup_count": 1,
        "default_enabled": False,
    },
    "soc": {
        "label": "SoC log",
        "format": "detailed",
        "backup_count": 1,
        "default_enabled": False,
    },
    "internal_chargepoint": {
        "label": "Internal chargepoint log",
        "format": "detailed",
        "backup_count": 1,
        "default_enabled": False,
    },
    # Not in any released openWB version yet -- taken from
    # openWB/core PR #3782 (open, not merged, as of writing). Update this
    # entry (or remove it) once that lands for real, in case anything
    # changes before merge.
    "forecast": {
        "label": "Forecast log",
        "format": "detailed",
        "backup_count": 1,
        "default_enabled": False,
    },
}

DEFAULT_ENABLED = [name for name, meta in CATALOG.items() if meta["default_enabled"]]
