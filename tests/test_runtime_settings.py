import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.runtime_settings import ValidationError, validate


def test_validate_accepts_a_full_valid_patch():
    clean = validate({
        "openwb_base_url": "http://10.1.5.32/",
        "openwb_ramdisk_path": "/openWB/ramdisk/",
        "enabled_sources": ["main", "chargelog"],
        "fetch_interval_seconds": 600,
        "retention_days": 30,
    })
    assert clean["openwb_base_url"] == "http://10.1.5.32"
    assert clean["openwb_ramdisk_path"] == "/openWB/ramdisk"
    assert clean["enabled_sources"] == ["main", "chargelog"]
    assert clean["fetch_interval_seconds"] == 600
    assert clean["retention_days"] == 30


def test_validate_only_touches_provided_keys():
    clean = validate({"retention_days": 7})
    assert clean == {"retention_days": 7}


def test_validate_rejects_base_url_without_scheme():
    with pytest.raises(ValidationError):
        validate({"openwb_base_url": "10.1.5.32"})


def test_validate_rejects_ramdisk_path_without_leading_slash():
    with pytest.raises(ValidationError):
        validate({"openwb_ramdisk_path": "openWB/ramdisk"})


def test_validate_rejects_empty_enabled_sources():
    with pytest.raises(ValidationError):
        validate({"enabled_sources": []})


def test_validate_rejects_unknown_source():
    with pytest.raises(ValidationError):
        validate({"enabled_sources": ["not_a_real_log"]})


def test_validate_rejects_fetch_interval_out_of_range():
    with pytest.raises(ValidationError):
        validate({"fetch_interval_seconds": 10})


def test_validate_rejects_retention_days_out_of_range():
    with pytest.raises(ValidationError):
        validate({"retention_days": 0})
