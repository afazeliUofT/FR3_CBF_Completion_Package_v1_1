#!/usr/bin/env python3
"""Independent audit of the retrieved, already-completed R2 holdout return."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import re
import sys

EXPECTED = {
    "point": 0.2504676932746432,
    "lower": 0.20132723612261208,
    "upper": 0.31024908237228865,
}


def read_json(path: Path) -> object:
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def close(a: float, b: float, tol: float = 1e-12) -> bool:
    return math.isfinite(float(a)) and abs(float(a) - float(b)) <= tol


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--return-root", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()
    root = Path(args.return_root).resolve()

    metadata = read_json(root / "RETURN_METADATA.json")
    require(metadata["pass_array_job_id"] == "18232438", "pass-array job binding mismatch")
    require(metadata["assembly_job_id"] == "18232439", "assembly job binding mismatch")
    require(metadata["seed_rerun_list"] == [44052], "seed scope mismatch")
    require(metadata["channel_regenerated"] is False, "channel was regenerated")
    require(metadata["gpu_requested"] is False, "GPU was requested")
    require(metadata["scientific_source_files_modified"] is False, "scientific source changed")
    require(metadata["action_library_definition_changed"] is False, "action library changed")
    require(metadata["automatic_extra_seeds_authorized"] is False, "extra seeds were authorized")

    completion = read_json(root / "HOLDOUT_COMPLETION_AUDIT.json")
    require(completion["status"] == "PASS_COMPLETED_FRESH_V4_5_HOLDOUT_AFTER_NONSCIENTIFIC_REPAIR", "completion audit status mismatch")
    require(completion["paper_writing_authorized"] is True, "paper writing not authorized")
    require(completion["automatic_extra_seeds_authorized"] is False, "extra seeds authorized")
    require(completion["automatic_algorithm_tuning_authorized"] is False, "algorithm tuning authorized")
    require(completion["next_gate"] == "FINALIZE_13_PAGE_TWC_MANUSCRIPT_AND_ONE_COMPACT_PRACTICALITY_SECTION", "next gate mismatch")
    facts = completion["source_supported_facts"]
    require(int(facts["seed_count"]) == 30, "seed count mismatch")
    require(int(facts["cell_count"]) == 1350, "cell count mismatch")
    require(facts["safety_gates_pass"] is True, "safety gate failed")
    require(facts["primary_superiority_met"] is True, "primary superiority not met")
    require(facts["floor_zero"] is False, "unexpected universal floor result")
    require(close(facts["primary_point_estimate"], EXPECTED["point"]), "primary point estimate mismatch")
    require(close(facts["primary_lower_95"], EXPECTED["lower"]), "primary lower CI mismatch")
    require(close(facts["primary_upper_95"], EXPECTED["upper"]), "primary upper CI mismatch")
    require(int(facts["long_eess_violation_seconds"]) == 0, "long EESS violations present")
    require(int(facts["short_eess_violation_seconds"]) == 0, "short EESS violations present")
    require(int(facts["network_wide_shutdown_intervals"]) == 0, "network-wide shutdown present")
    require(int(facts["q0_envelope_deployable_actions"]) == 0, "q0 deployable action used")

    merged = read_json(root / "merged" / "PHASE1_MERGED_AUDIT.json")
    require(int(merged["seed_count"]) == 30, "merged seed count mismatch")
    require(int(merged["cell_count"]) == 1350, "merged cell count mismatch")
    require(merged["valid_holdout_result"] is True, "merged holdout invalid")
    require(merged["safety_gates_pass"] is True, "merged safety gate failed")
    require(merged["primary_superiority_met"] is True, "merged primary superiority not met")
    require(merged["floor_zero"] is False, "merged floor-zero flag mismatch")
    primary = merged["primary_bootstrap"]
    require(close(primary["point_estimate"], EXPECTED["point"]), "merged point estimate mismatch")
    require(close(primary["lower_95"], EXPECTED["lower"]), "merged lower CI mismatch")
    require(close(primary["upper_95"], EXPECTED["upper"]), "merged upper CI mismatch")

    seed_result = read_json(root / "seed_44052" / "result" / "SEED_RESULT.json")
    require(int(seed_result["campaign_seed"]) == 44052, "seed result identity mismatch")
    require(int(seed_result["scientific_exit_code"]) == 42, "seed scientific exit mismatch")
    require(seed_result["candidate_hard_gates_pass"] is False, "seed 44052 hard-gate flag mismatch")

    overlay = read_json(root / "seed_44052" / "result" / "IMPLEMENTATION_CAPACITY_OVERLAY.json")
    require(overlay["classification"] == "IMPLEMENTATION_CAPACITY_REPAIR_NOT_ALGORITHM_TUNING", "capacity overlay classification mismatch")
    require(overlay["action_library_definition_changed"] is False, "capacity overlay changed action library")

    pass_dirs = sorted((root / "pass_outputs").glob("pass_*"))
    require([p.name for p in pass_dirs] == [f"pass_{i}" for i in range(5)], "five pass outputs not present")

    slurm = (root / "slurm" / "sacct_completion_r2.txt").read_text(encoding="utf-8", errors="replace")
    expected_elapsed = {0: "00:02:12", 1: "00:02:56", 2: "00:12:49", 3: "00:13:42", 4: "00:12:09"}
    for slot, elapsed in expected_elapsed.items():
        pattern = rf"^18232438_{slot}\|[^\n]*\|COMPLETED\|0:0\|{re.escape(elapsed)}\|"
        require(re.search(pattern, slurm, flags=re.MULTILINE) is not None, f"pass {slot} Slurm record mismatch")
    require(re.search(r"^18232439\|[^\n]*\|COMPLETED\|0:0\|00:00:18\|", slurm, flags=re.MULTILINE) is not None, "assembly Slurm record mismatch")

    index_path = root / "merged" / "PHASE1_SEED_RESULT_HASH_INDEX.csv"
    with index_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    require(len(rows) == 30, "seed hash index does not contain 30 rows")
    seeds = sorted(int(row["campaign_seed"]) for row in rows)
    require(seeds == list(range(44030, 44060)), "seed hash index range mismatch")

    table = (root / "holdout_key_results.tex").read_text(encoding="utf-8")
    require("0.2505" in table and "0.2013" in table and "0.3102" in table, "paper-facing table does not contain final estimates")

    audit = {
        "schema_version": 1,
        "status": "PASS_RETRIEVED_COMPLETED_V45_HOLDOUT_R2",
        "source_supported_facts": {
            "pass_array_job_id": "18232438",
            "assembly_job_id": "18232439",
            "pass_task_completed_count": 5,
            "seed_count": 30,
            "cell_count": 1350,
            "seed_safety_pass_count": 30,
            "seed_zero_floor_pass_count": int(merged["seed_hard_gate_pass_count"]),
            "primary_point_estimate": float(primary["point_estimate"]),
            "primary_lower_95": float(primary["lower_95"]),
            "primary_upper_95": float(primary["upper_95"]),
            "primary_superiority_met": bool(merged["primary_superiority_met"]),
            "floor_zero": bool(merged["floor_zero"]),
            "floor_violation_user_seconds": int(facts["floor_violation_user_seconds"]),
            "floor_violation_user_intervals": int(facts["floor_violation_user_intervals"]),
            "maximum_normalized_floor_shortfall": float(facts["maximum_normalized_floor_shortfall"]),
            "floor_reduction_versus_predictive_percent": float(facts["floor_reduction_versus_predictive_percent"]),
            "floor_reduction_versus_static_percent": float(facts["floor_reduction_versus_static_percent"]),
            "long_eess_violation_seconds": 0,
            "short_eess_violation_seconds": 0,
            "unresolved_intervals": int(facts["unresolved_intervals"]),
            "network_wide_shutdown_intervals": 0,
            "q0_envelope_deployable_actions": 0,
            "seed_44052_scientific_exit_code": 42,
            "seed_44052_candidate_hard_gates_pass": False,
        },
        "scientific_inference": {
            "correct_claim": "EESS-safe statistically significant utility superiority with a feasibility-conditioned user-floor guarantee under the declared fixed-association bounded distributed action class",
            "universal_floor_claim_supported": False,
            "additional_simulation_required_before_manuscript": False,
        },
        "paper_writing_authorized": True,
        "automatic_extra_seeds_authorized": False,
        "automatic_algorithm_tuning_authorized": False,
        "next_gate": "FINALIZE_13_PAGE_TWC_MANUSCRIPT_AND_ONE_COMPACT_PRACTICALITY_SECTION",
    }
    output = Path(args.output_json).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("RETRIEVED_HOLDOUT_INDEPENDENT_AUDIT=PASS")
    print("HOLDOUT_RETURN_STATUS=PASS_FRESH_V4_5_HOLDOUT_SAFETY_AND_UTILITY_FEASIBILITY_CONDITIONED_FLOOR")
    print("HOLDOUT_VALID_RESULT=True")
    print("HOLDOUT_SEED_RETURN_COUNT=30")
    print("HOLDOUT_SEED_SAFETY_PASS_COUNT=30")
    print("HOLDOUT_SEED_ZERO_FLOOR_PASS_COUNT=" + str(int(merged["seed_hard_gate_pass_count"])))
    print("HOLDOUT_PRIMARY_SUPERIORITY_MET=True")
    print("HOLDOUT_FLOOR_ZERO=False")
    print("PRIMARY_POINT_ESTIMATE=" + str(primary["point_estimate"]))
    print("PRIMARY_LOWER_95=" + str(primary["lower_95"]))
    print("PRIMARY_UPPER_95=" + str(primary["upper_95"]))
    print("FLOOR_VIOLATION_USER_SECONDS=" + str(int(facts["floor_violation_user_seconds"])))
    print("FLOOR_VIOLATION_USER_INTERVALS=" + str(int(facts["floor_violation_user_intervals"])))
    print("MAXIMUM_NORMALIZED_FLOOR_SHORTFALL=" + str(float(facts["maximum_normalized_floor_shortfall"])))
    print("FLOOR_REDUCTION_VS_PREDICTIVE_PERCENT=" + str(float(facts["floor_reduction_versus_predictive_percent"])))
    print("FLOOR_REDUCTION_VS_STATIC_PERCENT=" + str(float(facts["floor_reduction_versus_static_percent"])))
    print("UNRESOLVED_INTERVALS=" + str(int(facts["unresolved_intervals"])))
    print("PAPER_WRITING_AUTHORIZED=True")
    print("AUTOMATIC_EXTRA_SEEDS_AUTHORIZED=NO")
    print("AUTOMATIC_ALGORITHM_TUNING_AUTHORIZED=NO")
    print("NEXT_GATE=FINALIZE_13_PAGE_TWC_MANUSCRIPT_AND_ONE_COMPACT_PRACTICALITY_SECTION")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"RETRIEVED_HOLDOUT_INDEPENDENT_AUDIT=FAIL:{exc}", file=sys.stderr)
        raise
