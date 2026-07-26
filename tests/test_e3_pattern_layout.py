from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sa509_physical_parameters_and_continuity():
    mod = load("layout_mod", "scripts/23_2_prepare_e3_pattern_layout.py")
    for multiple in [False, True]:
        params = mod.sa509_parameters(13.0, 8.15, 0.65, multiple)
        assert params["d_over_lambda"] > 100
        assert 58 < params["g0_dbi"] < 60
        assert 0 < params["phi0_deg"] < params["phi1_deg"] < params["phi2_deg"] < 1
        eps = 1e-9
        for boundary in [params["phi1_deg"], params["phi2_deg"]]:
            left = float(mod.sa509_gain(boundary - eps, params, multiple))
            right = float(mod.sa509_gain(boundary, params, multiple))
            assert abs(left - right) < 1e-4
        # SA.509 uses rounded piecewise constants at 48 degrees and
        # deliberately different plateaus at 80 and 120 degrees; those are
        # checked as exact branch values rather than false continuity claims.


def test_sa509_known_plateaus():
    mod = load("layout_mod2", "scripts/23_2_prepare_e3_pattern_layout.py")
    p_mult = mod.sa509_parameters(13.0, 8.15, 0.65, True)
    p_single = mod.sa509_parameters(13.0, 8.15, 0.65, False)
    assert float(mod.sa509_gain(60.0, p_mult, True)) == -13.0
    assert float(mod.sa509_gain(100.0, p_mult, True)) == -8.0
    assert float(mod.sa509_gain(150.0, p_mult, True)) == -13.0
    assert float(mod.sa509_gain(60.0, p_single, False)) == -10.0
    assert float(mod.sa509_gain(100.0, p_single, False)) == -5.0


def test_layout_count_spacing_and_station_clearance():
    mod = load("layout_mod3", "scripts/23_2_prepare_e3_pattern_layout.py")
    rows = mod.local_layout(500.0, 3000.0, 180.0, 30.0)
    assert len(rows) == 19
    points = np.array([[row["east_m"], row["north_m"]] for row in rows])
    distances = []
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            distances.append(float(np.linalg.norm(points[i] - points[j])))
    assert abs(min(distances) - 500.0) < 1e-9
    station_distances = np.linalg.norm(points, axis=1)
    assert abs(float(station_distances.min()) - 2000.0) < 1e-9
    assert abs(float(station_distances.max()) - 4000.0) < 1e-9


def test_angular_separation_known_cases():
    mod = load("layout_mod4", "scripts/23_2_prepare_e3_pattern_layout.py")
    zero = mod.angular_separation_deg(np.array([0.0]), np.array([0.0]), 0.0, 0.0)
    ninety = mod.angular_separation_deg(np.array([90.0]), np.array([0.0]), 0.0, 0.0)
    zenith = mod.angular_separation_deg(np.array([0.0]), np.array([90.0]), 0.0, 0.0)
    assert abs(float(zero[0])) < 1e-10
    assert abs(float(ninety[0]) - 90.0) < 1e-10
    assert abs(float(zenith[0]) - 90.0) < 1e-10


def test_pdf_validation_rejects_html_and_short_files():
    mod = load("fetch_mod", "scripts/23_0_fetch_sa509.py")
    for data in [b"<html>not pdf</html>", b"%PDF-1.4\n%%EOF"]:
        try:
            mod.validate_pdf_bytes(data)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid PDF payload was not rejected")


def test_manifest_format_and_exclusions(tmp_path: Path):
    mod = load("manifest_mod", "scripts/23_1_rebuild_e3_intake_evidence.py")
    required = [
        "E3_REFERENCE_INTAKE_MANIFEST.sha256",
        "config/e3_reference_intake.yaml",
        "scripts/22_0_rebuild_p452_pilot_evidence.py",
        "scripts/22_1_prepare_e3_station.py",
        "scripts/22_2_fetch_validate_e3_tle.py",
        "scripts/22_3_generate_select_e3_pass.py",
        "RUN_E3_REFERENCE_INTAKE.sh",
        "logs/22_0_rebuild_p452_pilot_evidence.log",
        "logs/22_1_prepare_e3_station.log",
        "logs/22_2_fetch_validate_e3_tle.log",
        "logs/22_3_generate_select_e3_pass.log",
    ]
    for rel in required:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
    for rel in ["data/real/e3_reference_case/a.csv", "data/external/tle/a.tle", "data/external/mrdem_e3_reference/a.tif"]:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
    bad = tmp_path / "data/external/tle/README.md:Zone.Identifier"
    bad.write_text("bad", encoding="utf-8")
    output = tmp_path / "data/real/E3_REFERENCE_INTAKE_EVIDENCE.sha256"
    lines = mod.build_manifest(tmp_path, output)
    assert lines
    assert all(mod.LINE_RE.fullmatch(line) for line in lines)
    assert all("Zone.Identifier" not in line for line in lines)


def test_prepare_and_freeze_end_to_end_with_synthetic_raster(tmp_path: Path):
    import pandas as pd
    import rasterio
    import yaml
    from rasterio.transform import from_origin

    mod = load("layout_integration", "scripts/23_2_prepare_e3_pattern_layout.py")
    # Copy and adapt the shipped configuration into the temporary project root.
    cfg = yaml.safe_load((ROOT / "config/e3_pattern_layout.yaml").read_text(encoding="utf-8"))
    cfg_path = tmp_path / "config/e3_pattern_layout.yaml"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")

    station_dir = tmp_path / "data/real/e3_reference_case"
    station_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{
        "station_id": "TEST_STATION",
        "latitude_deg": 45.58526,
        "longitude_deg": -75.80877,
        "ground_elevation_m_asl": 270.0,
        "phase_center_height_m_agl_nominal": 20.0,
        "altitude_m_asl": 290.0,
        "dish_diameter_m": 13.0,
        "dish_gain_dbi": "",
        "minimum_elevation_deg": 5.0,
        "antenna_pattern_source": "OPEN",
        "target_mission": "TEST",
        "field_status": "MODEL",
        "source_url": "https://example.invalid",
        "provenance_note": "synthetic test",
    }]).to_csv(station_dir / "earth_station_staging.csv", index=False)
    (station_dir / "E3_STATION_SOURCE_RECORD.json").write_text("{}\n", encoding="utf-8")
    (station_dir / "E3_PASS_SELECTION.json").write_text(json.dumps({
        "next_gate": "EARTH_STATION_PATTERN_AND_CELLULAR_LAYOUT_FREEZE",
        "selected_pass": {"complete_within_search_window": True},
    }) + "\n", encoding="utf-8")
    t = np.arange(0, 21, dtype=float)
    pd.DataFrame({
        "time_utc": [f"2026-01-01T00:00:{int(x):02d}+00:00" for x in t],
        "time_s": t,
        "azimuth_deg": np.linspace(100, 200, len(t)),
        "elevation_deg": 5 + 30 * np.sin(np.linspace(0, math.pi, len(t))),
        "slant_range_km": np.linspace(1500, 600, len(t)),
    }).to_csv(station_dir / "e3_track_selected_pass_1s.csv", index=False)

    itu_dir = tmp_path / "data/external/itu"
    itu_dir.mkdir(parents=True, exist_ok=True)
    pdf = b"%PDF-1.4\n" + b"0" * 120_000 + b"\n%%EOF\n"
    (itu_dir / "R-REC-SA.509-3-201312-I!!PDF-E.pdf").write_bytes(pdf)
    (itu_dir / "SA509_SOURCE_RECORD.json").write_text("{}\n", encoding="utf-8")

    dem_dir = tmp_path / "data/external/mrdem_e3_layout"
    dem_dir.mkdir(parents=True, exist_ok=True)
    # WGS84 raster covering more than the full 4 km layout radius.
    width = height = 500
    resolution = 0.0002
    transform = from_origin(-75.86, 45.63, resolution, resolution)
    data = np.full((height, width), 250.0, dtype=np.float32)
    with rasterio.open(
        dem_dir / "mrdem_dtm_study_subset.tif",
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        nodata=-9999.0,
    ) as dst:
        dst.write(data, 1)
    (dem_dir / "MRDEM_SOURCE_RECORD.json").write_text("{}\n", encoding="utf-8")

    assert mod.main(["--root", str(tmp_path), "--config", "config/e3_pattern_layout.yaml"]) == 0
    review = tmp_path / "data/real/e3_pattern_layout_review"
    assert (review / "bs_sites_review.csv").is_file()
    assert len(pd.read_csv(review / "bs_sites_review.csv")) == 19
    assert len(pd.read_csv(review / "bs_sectors_review.csv")) == 57
    audit = json.loads((review / "E3_PATTERN_LAYOUT_AUDIT.json").read_text(encoding="utf-8"))
    assert audit["status"] == "REVIEW_REQUIRED"

    cfg["manual_confirmations"] = {key: True for key in cfg["manual_confirmations"]}
    cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    assert mod.main(["--root", str(tmp_path), "--config", "config/e3_pattern_layout.yaml", "--confirm"]) == 0
    assert len(pd.read_csv(tmp_path / "data/real/bs_sites.csv")) == 19
    assert len(pd.read_csv(tmp_path / "data/real/bs_sectors.csv")) == 57
    decision = json.loads((tmp_path / "data/real/E3_PATTERN_LAYOUT_DECISION.json").read_text(encoding="utf-8"))
    assert decision["status"] == "FROZEN"
    assert decision["next_gate"] == "FIRST_CELLULAR_SECTOR_TO_EARTH_STATION_P452_PATH"
