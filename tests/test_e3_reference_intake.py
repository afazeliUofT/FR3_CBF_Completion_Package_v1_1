from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_tle_line(prefix: str) -> str:
    base = prefix.ljust(68)
    total = sum(int(c) for c in base if c.isdigit()) + base.count("-")
    return base + str(total % 10)


def test_checksum_and_epoch_parser():
    mod = load("tle", "scripts/22_2_fetch_validate_e3_tle.py")
    line1 = make_tle_line("1 44322U 19036A   26100.50000000  .00000000  00000-0  00000-0 0  999")
    line2 = make_tle_line("2 44322  97.8000 100.0000 0001000 100.0000 260.0000 14.900000001234")
    assert mod.checksum_ok(line1)
    assert mod.checksum_ok(line2)
    name, p1, p2, epoch = mod.parse_tle(f"RCM 1\n{line1}\n{line2}\n", 44322)
    assert name == "RCM 1"
    assert p1 == line1 and p2 == line2
    assert epoch.tzinfo == timezone.utc


def test_reject_wrong_catalog():
    mod = load("tle2", "scripts/22_2_fetch_validate_e3_tle.py")
    line1 = make_tle_line("1 44322U 19036A   26100.50000000  .00000000  00000-0  00000-0 0  999")
    line2 = make_tle_line("2 44322  97.8000 100.0000 0001000 100.0000 260.0000 14.900000001234")
    try:
        mod.parse_tle(f"RCM 1\n{line1}\n{line2}\n", 12345)
    except ValueError:
        pass
    else:
        raise AssertionError("wrong catalog was not rejected")


def test_pass_segmentation_complete_and_partial():
    mod = load("passes", "scripts/22_3_generate_select_e3_pass.py")
    df = pd.DataFrame(
        {
            "time_utc": [f"2026-01-01T00:00:{i:02d}+00:00" for i in range(10)],
            "time_s": list(range(10)),
            "elevation_deg": [0, 6, 10, 6, 0, 0, 7, 9, 8, 7],
        }
    )
    cat = mod.complete_passes(df, 5.0)
    assert len(cat) == 2
    assert bool(cat.iloc[0]["complete_within_search_window"]) is True
    assert bool(cat.iloc[1]["complete_within_search_window"]) is False
    assert cat.iloc[0]["max_elevation_deg"] == 10.0


def test_tle_checksum_rejects_mutation():
    mod = load("tle3", "scripts/22_2_fetch_validate_e3_tle.py")
    line = make_tle_line("1 44322U 19036A   26100.50000000  .00000000  00000-0  00000-0 0  999")
    bad = line[:-1] + str((int(line[-1]) + 1) % 10)
    assert not mod.checksum_ok(bad)
