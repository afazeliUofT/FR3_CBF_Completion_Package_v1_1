from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_configuration_counts():
    cfg = json.loads(
        (ROOT / "config/sionna2_channel_qualification.json").read_text(
            encoding="utf-8"
        )
    )
    expected = cfg["expected"]
    assert expected["pilot_num_rings"] == 1
    assert expected["pilot_bs_sectors"] == 21
    assert expected["pilot_users"] == 21
    assert expected["pilot_bs_antenna_count"] == 8


def test_scenario_heights_are_model_consistent():
    cfg = json.loads(
        (ROOT / "config/sionna2_channel_qualification.json").read_text(
            encoding="utf-8"
        )
    )
    assert cfg["pilot_scenarios"]["uma"]["bs_height_m"] == 25.0
    assert cfg["pilot_scenarios"]["umi"]["bs_height_m"] == 10.0


def test_top_level_versions_pinned():
    lines = {
        line.strip()
        for line in (
            ROOT / "requirements/sionna2_channel_qualification.txt"
        ).read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    assert "torch==2.9.1" in lines
    assert "sionna-no-rt==2.0.1" in lines
