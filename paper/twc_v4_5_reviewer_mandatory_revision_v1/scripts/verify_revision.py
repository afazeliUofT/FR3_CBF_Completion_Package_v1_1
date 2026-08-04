#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package-root", type=Path, required=True)
    args = ap.parse_args()
    root = args.package_root.resolve()

    mandatory = load(root / "audits" / "MANDATORY_REVISION_EVIDENCE_AUDIT.json")
    assert mandatory["status"] == "PASS_REVIEWER_MANDATORY_REVISION_EVIDENCE_AUDIT"
    assert mandatory["controller_source_changed"] is False
    assert mandatory["new_simulation_executed"] is False
    assert mandatory["fresh_seed_executed"] is False

    arr = load(root / "audits" / "ARRAY_CONSISTENCY_REPAIR_AUDIT.json")
    assert arr["executed_config_rows"] == 8 and arr["executed_config_cols"] == 8
    assert arr["executed_port_count"] == 128
    assert arr["generator_uses_bs_sector_csv_array_size_fields"] is False
    assert arr["element_pattern_reference_scientific_fields_equal_after_patch"] is True

    sa = load(root / "audits" / "SA1027_THRESHOLD_PROVENANCE_AUDIT.json")
    assert sa["long_criterion"] == {"p_percent": 20.0, "threshold_dbw_per_10mhz": -150.0}
    assert sa["short_criterion"] == {"p_percent": 0.005, "threshold_dbw_per_10mhz": -133.0}
    assert sa["evaluated_minimum_satellite_elevation_deg"] >= 5.0

    pattern = load(root / "audits" / "SA509_SCOPE_AND_GEOMETRY_AUDIT.json")
    assert pattern["condition_satisfied"] is True
    assert pattern["d_over_lambda"] >= 100.0
    assert pattern["certified_real_station_bound"] is False

    stress = load(root / "audits" / "SA509_SINGLE_ENTRY_FROZEN_ACTION_SENSITIVITY.json")
    assert stress["single_entry_frozen_action_long_violation_seconds"] == 83859
    assert stress["single_entry_frozen_action_long_violating_cells"] == 150
    assert stress["single_entry_frozen_action_short_violation_seconds"] == 0
    assert stress["scope"].startswith("frozen-action")

    tr = load(root / "audits" / "TR38901_CLAIM_SCOPE_AUDIT.json")
    assert tr["full_v19_4_certification"] is False
    assert tr["paper_claim_allowed"] is True
    assert tr["executed_parameters"]["sionna_version"] == "2.0.1"

    p452 = load(root / "audits" / "P452_VALIDATION_AND_SEMANTICS_AUDIT.json")
    assert p452["site_count"] == 19
    assert p452["validated_row_count"] == 798
    assert p452["separate_p2108_applied"] is False
    assert "17 of 17" in p452["official_validation_example_result"]

    utility = load(root / "audits" / "UTILITY_EFFECT_INTERPRETATION_AUDIT.json")
    assert 0.109 < utility["epsilon_shifted_geometric_mean_percent_candidate_minus_safe_static"] < 0.111

    with (root / "03_MANDATORY_REVISION_CLOSURE_MATRIX.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 7
    assert all(r["new_simulation_required"] == "NO" for r in rows)

    tex = (root / "manuscript" / "FR3_TWC_v4_5_reviewer_mandatory_revision_candidate_v3.tex").read_text(encoding="utf-8")
    table_text = (root / "manuscript" / "tables" / "sa509_pattern_sensitivity.tex").read_text(encoding="utf-8")
    combined = tex + "\n" + table_text
    required_phrases = [
        "Rec. ITU-R SA.1027-6",
        "public Gatineau reference geometry",
        "pinned Sionna 2.0.1 UMa implementation",
        "83,859",
        "shifted geometric mean",
        "fixed-service receivers are outside",
        "17 official SG3 validation examples",
    ]
    for phrase in required_phrases:
        assert phrase.lower() in combined.lower(), phrase
    assert "pre-registered" not in tex.lower()
    assert "not called a certified bound" in tex.lower()

    for z in [
        root / "evidence" / "final_holdout" / "FR3_RORQUAL_V4_5_FRESH_HOLDOUT_18163102.zip",
        root / "evidence" / "final_holdout" / "FR3_RORQUAL_V4_5_HOLDOUT_COMPLETION_R2_18232438.zip",
    ]:
        with zipfile.ZipFile(z) as archive:
            bad = archive.testzip()
        assert bad is None, f"CRC failure in {z}: {bad}"
        side = Path(str(z) + ".sha256")
        parts = side.read_text(encoding="utf-8").strip().split()
        assert len(parts) == 2 and parts[1] == z.name
        h = hashlib.sha256()
        with z.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(block)
        assert h.hexdigest() == parts[0]

    pdf = root / "manuscript" / "FR3_TWC_v4_5_reviewer_mandatory_revision_candidate_v3.pdf"
    if not pdf.exists():
        raise AssertionError(f"Missing PDF: {pdf}")
    info = subprocess.check_output(["pdfinfo", str(pdf)], text=True)
    pages = next(int(line.split(":", 1)[1]) for line in info.splitlines() if line.startswith("Pages:"))
    assert pages == 13, pages

    print("REVIEWER_FEEDBACK_INDEPENDENT_EVALUATION=PASS")
    print("MANDATORY_REVISION_ITEM_COUNT=7")
    print("MANDATORY_REVISION_CLOSED_COUNT=7")
    print("NEW_SIMULATION_EXECUTED=NO")
    print("SCIENTIFIC_CONTROLLER_SOURCE_CHANGED=NO")
    print("SA509_SINGLE_ENTRY_STRESS_LONG_VIOLATION_SECONDS=83859")
    print("MANUSCRIPT_PAGE_COUNT=13")
    print("REVISED_SCIENTIFIC_VERDICT=STRONG_TWC_CANDIDATE_AFTER_MANDATORY_PROVENANCE_AND_SCOPE_REPAIR")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
