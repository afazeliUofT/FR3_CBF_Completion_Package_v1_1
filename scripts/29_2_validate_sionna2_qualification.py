#!/usr/bin/env python3
"""Strictly validate the clean Sionna 2.0.1 channel qualification."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default="config/sionna2_channel_qualification.json"
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    work = ROOT / cfg["environment"]["work_dir"]
    source_decision = json.loads(
        (work / "CHANNEL_SOURCE_REVIEW_DECISION.json").read_text(encoding="utf-8")
    )
    audit = json.loads(
        (work / "SIONNA2_API_QUALIFICATION_AUDIT.json").read_text(encoding="utf-8")
    )
    expected = cfg["expected"]

    assert source_decision["status"] == "NO_REUSABLE_EXECUTABLE_CHANNEL_BASELINE_FOUND"
    assert audit["status"] == "PASS_ENVIRONMENT_AND_API_QUALIFICATION"
    assert audit["environment"]["torch_base_version"] == str(
        expected["torch_version"]
    )
    assert audit["environment"]["sionna_version"] == str(expected["sionna_version"])
    assert audit["environment"]["torch_device_used"] == "cpu"
    assert audit["seeded_uma_reproducibility"]["passed"] is True

    for name, expected_height in [("uma", 25.0), ("umi", 10.0)]:
        summary = audit[name]
        assert summary["topology_shapes"]["ut_loc"] == [
            1,
            int(expected["pilot_users"]),
            3,
        ]
        assert summary["topology_shapes"]["bs_loc"] == [
            1,
            int(expected["pilot_bs_sectors"]),
            3,
        ]
        assert summary["array"]["bs_num_ant"] == int(
            expected["pilot_bs_antenna_count"]
        )
        assert summary["array"]["ut_num_ant"] == int(
            expected["pilot_ut_antenna_count"]
        )
        assert summary["channel_shapes"]["coefficients"][1] == int(
            expected["pilot_users"]
        )
        assert summary["channel_shapes"]["coefficients"][3] == int(
            expected["pilot_bs_sectors"]
        )
        assert summary["channel_statistics"]["nonzero_path_energy_fraction"] > 0
        heights = summary["topology_statistics"]["bs_height_unique_m"]
        assert len(heights) == 1 and abs(float(heights[0]) - expected_height) < 1e-5

    validation = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_CLEAN_SIONNA_2_0_1_IMPLEMENTATION_CANDIDATE",
        "claim_boundary": cfg["claim_boundary"]["implementation_decision"],
        "no_reusable_legacy_channel_engine_found": True,
        "sionna_2_0_1_cpu_api_qualification": True,
        "uma_25m_topology_verified": True,
        "umi_10m_topology_verified": True,
        "seeded_reproducibility_verified": True,
        "exact_tr_138_901_v19_4_0_mapping_complete": False,
        "paper_scale_gpu_execution_complete": False,
        "next_gate": cfg["next_gate"],
    }
    write_json(work / "SIONNA2_CHANNEL_QUALIFICATION_VALIDATION.json", validation)
    (work / "SIONNA2_CHANNEL_QUALIFICATION_VALIDATION.md").write_text(
        "# Clean Sionna 2.0.1 channel qualification\n\n"
        f"- Status: `{validation['status']}`\n"
        "- Legacy executable channel engine: not found in the reviewed source root\n"
        "- Sionna 2.0.1 / PyTorch 2.9.1 CPU API pilot: passed\n"
        "- UMa pilot height: 25 m\n"
        "- UMi pilot height: 10 m\n"
        "- Seeded UMa reproducibility: passed\n"
        "- Exact TR 38.901 V19.4.0 clause mapping: still required\n"
        "- Paper-scale GPU run: not yet performed\n\n"
        f"Next gate: `{validation['next_gate']}`\n",
        encoding="utf-8",
    )
    print("SIONNA 2.0.1 CHANNEL QUALIFICATION VALIDATION: PASS")
    print(json.dumps(validation, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
