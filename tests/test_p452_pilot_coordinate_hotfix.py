from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
PREP_PATH = ROOT / "scripts" / "21_0_prepare_p452_pilot.py"
PREFLIGHT_PATH = ROOT / "scripts" / "21_2_preflight_p452_pilot_inputs.py"
MATLAB_PATH = ROOT / "matlab" / "run_p452_pilot.m"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PREP = load_module("p452_pilot_prepare_coordinate", PREP_PATH)
PREFLIGHT = load_module("p452_pilot_input_preflight", PREFLIGHT_PATH)


def test_signed_western_longitude_is_preserved() -> None:
    assert PREP.validate_longitude_deg(-79.01522222, "tx_lon") == -79.01522222


@pytest.mark.parametrize("value", [181.0, -181.0, 281.08330556, float("inf")])
def test_out_of_range_longitude_is_rejected(value: float) -> None:
    with pytest.raises(ValueError, match=r"\[-180, 180\]"):
        PREP.validate_longitude_deg(value, "longitude")


def test_preparation_source_never_wraps_longitude_to_360() -> None:
    source = PREP_PATH.read_text(encoding="utf-8")
    assert "% 360" not in source
    assert "tx_longitude_deg\": tx_longitude_deg" in source
    assert "rx_longitude_deg\": rx_longitude_deg" in source


def test_matlab_runner_has_signed_coordinate_preflight_and_correct_order() -> None:
    source = MATLAB_PATH.read_text(encoding="utf-8")
    assert "P452_GEOGRAPHIC_COORDINATE_PREFLIGHT: PASS" in source
    assert "P.452 longitudes must be in signed degrees within [-180, 180]" in source
    call_fragment = (
        "params.tx_longitude_deg, params.tx_latitude_deg, ...\n"
        "            params.rx_longitude_deg, params.rx_latitude_deg, ..."
    )
    assert call_fragment in source


def write_frozen_fixture(root: Path, *, tx_lon: float = -78.91669444) -> None:
    root.mkdir(parents=True)
    parameters = {
        "coordinate_convention": PREFLIGHT.COORDINATE_CONVENTION,
        "tl_p452_coordinate_argument_order": PREFLIGHT.COORDINATE_ARGUMENT_ORDER,
        "coordinate_tolerance_deg": 1e-7,
        "tx_longitude_deg": tx_lon,
        "tx_latitude_deg": 44.11205556,
        "rx_longitude_deg": -79.01522222,
        "rx_latitude_deg": 44.31413889,
        "p452_polarization_codes": [1, 2],
        "p452_polarization_labels": ["H", "V"],
    }
    (root / "p452_pilot_parameters.json").write_text(
        json.dumps(parameters), encoding="utf-8"
    )
    audit = {
        "status": "MATLAB_READY_FROZEN",
        "manual_confirmations": {
            "profile_plot_reviewed": True,
            "path_has_no_p452_sea_segment": True,
            "tx_is_at_least_5km_from_sea_coast": True,
            "rx_is_at_least_5km_from_sea_coast": True,
            "understood_pipeline_only_status": True,
        },
    }
    (root / "P452_PILOT_PREP_AUDIT.json").write_text(
        json.dumps(audit), encoding="utf-8"
    )
    pd.DataFrame(
        {
            "distance_km": [0.0, 1.0, 2.0, 3.0],
            "terrain_m_asl": [100.0, 101.0, 102.0, 103.0],
            "clutter_plus_terrain_m_asl": [100.0, 101.0, 102.0, 103.0],
            "radio_climatic_zone": [2, 2, 2, 2],
            "longitude_deg": [
                -78.91669444,
                -78.95,
                -78.98,
                -79.01522222,
            ],
            "latitude_deg": [44.11205556, 44.18, 44.25, 44.31413889],
        }
    ).to_csv(root / "p452_pilot_profile.csv", index=False)


def test_preflight_accepts_signed_western_longitudes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pilot = tmp_path / "pilot"
    write_frozen_fixture(pilot)
    monkeypatch.setattr(sys, "argv", ["preflight", "--pilot-dir", str(pilot)])
    assert PREFLIGHT.main() == 0
    assert "P.452 PILOT INPUT PREFLIGHT: PASS" in capsys.readouterr().out


def test_preflight_rejects_0_to_360_wrapped_western_longitude(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pilot = tmp_path / "pilot"
    write_frozen_fixture(pilot, tx_lon=281.08330556)
    monkeypatch.setattr(sys, "argv", ["preflight", "--pilot-dir", str(pilot)])
    with pytest.raises(ValueError, match=r"outside \[-180, 180\]"):
        PREFLIGHT.main()
