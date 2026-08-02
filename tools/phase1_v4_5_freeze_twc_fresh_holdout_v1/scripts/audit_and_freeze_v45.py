#!/usr/bin/env python3
"""Audit candidate-v4.5 development evidence and freeze the TWC claim policy."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import zipfile


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_sidecar(sidecar: Path, expected_digest: str, expected_name: str) -> None:
    lines = sidecar.read_text(encoding="utf-8").splitlines()
    if len(lines) != 1:
        raise ValueError(f"sidecar must have exactly one line: {sidecar}")
    parts = lines[0].split()
    if len(parts) != 2 or parts[0] != expected_digest or parts[1] != expected_name:
        raise ValueError(f"sidecar mismatch: {sidecar}")
    if Path(parts[1]).name != parts[1]:
        raise ValueError("sidecar must be basename-only")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--package-root", required=True)
    p.add_argument("--output-dir", required=True)
    args = p.parse_args()
    root = Path(args.package_root).resolve()
    out = Path(args.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    contract = json.loads((root / "config/FREEZE_HOLDOUT_CONTRACT.json").read_text(encoding="utf-8"))
    imm = root / "immutable_bindings"
    summary = json.loads((imm / "V45_COMPANION_AWARE_DEVELOPMENT_SUMMARY.json").read_text(encoding="utf-8"))
    sidecar = imm / "FR3_RORQUAL_V4_5_COMPANION_AWARE_DEVELOPMENT_18159228.zip.sha256"
    verify_sidecar(
        sidecar,
        contract["development_return_sha256"],
        "FR3_RORQUAL_V4_5_COMPANION_AWARE_DEVELOPMENT_18159228.zip",
    )

    expected = {
        "status": "V4_5_COMPANION_AWARE_SCHEDULING_DEVELOPMENT_INCOMPLETE",
        "all30_hard_gate_pass_count": 23,
        "all30_bounded_scope_pass_count": 30,
        "candidate_floor_violation_user_seconds": 6505,
        "candidate_floor_violation_user_intervals": 1312,
        "candidate_long_eess_violation_seconds": 0,
        "candidate_short_eess_violation_seconds": 0,
        "original_v4_3_unresolved_interval_count": 1736,
        "scheduling_success_interval_count": 1217,
        "scheduling_failure_interval_count": 519,
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            raise ValueError(f"development summary mismatch for {key}: {summary.get(key)!r} != {value!r}")
    if summary.get("fresh_holdout_required") is not True:
        raise ValueError("fresh holdout requirement is missing")
    if summary.get("information_exchange_locality_certified") is not False:
        raise ValueError("information-exchange claim boundary changed")

    job_zip = imm / "FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_5_HOLDOUT_v1.zip"
    job_sidecar = Path(str(job_zip) + ".sha256")
    if sha256_file(job_zip) != contract["job_package_sha256"]:
        raise ValueError("holdout job package hash mismatch")
    verify_sidecar(job_sidecar, contract["job_package_sha256"], job_zip.name)
    with zipfile.ZipFile(job_zip) as z:
        bad = z.testzip()
        if bad is not None:
            raise ValueError(f"holdout job package CRC failure: {bad}")
        with tempfile.TemporaryDirectory(prefix="fr3-v45-job-audit-") as tmp:
            z.extractall(tmp)
            job_root = Path(tmp)
            manifest = job_root / "PACKAGE_MANIFEST.sha256"
            if not manifest.is_file():
                raise ValueError("holdout job package manifest missing")
            for raw in manifest.read_text(encoding="utf-8").splitlines():
                if not raw.strip():
                    continue
                digest, rel = raw.split(maxsplit=1)
                rel = rel.lstrip(" *")
                path = job_root / rel
                if not path.is_file() or sha256_file(path) != digest:
                    raise ValueError(f"holdout job manifest mismatch: {rel}")
            job_contract = json.loads((job_root / "JOB_PACKAGE_CONTRACT.json").read_text(encoding="utf-8"))
            if job_contract["package_id"] != contract["job_package_id"]:
                raise ValueError("holdout job package ID mismatch")
            if job_contract["campaign_seed_list"] != contract["fresh_holdout_seeds"]:
                raise ValueError("holdout seed list mismatch")
            if job_contract["primary_method"] != contract["candidate_method_id"]:
                raise ValueError("candidate method binding mismatch")
            if job_contract["freeze_commit"] != contract["development_evidence_commit"]:
                raise ValueError("freeze commit mismatch")

    v44_residual = 523
    v45_residual = int(summary["scheduling_failure_interval_count"])
    marginal_closed = v44_residual - v45_residual
    marginal_percent = 100.0 * marginal_closed / v44_residual
    v43_floor = 19994
    predictive_floor = 90612
    static_floor = 105860
    v45_floor = int(summary["candidate_floor_violation_user_seconds"])
    metrics = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_FREEZE_V4_5_STOP_ALGORITHM_TUNING_AND_START_TWC",
        "development_role": "POST_ADAPTATION_DEVELOPMENT_NOT_FRESH_CONFIRMATION",
        "v45_hard_gate_pass_seeds": int(summary["all30_hard_gate_pass_count"]),
        "v45_bounded_scope_pass_seeds": int(summary["all30_bounded_scope_pass_count"]),
        "v45_floor_violation_user_seconds": v45_floor,
        "v45_residual_intervals": v45_residual,
        "v45_long_eess_violation_seconds": 0,
        "v45_short_eess_violation_seconds": 0,
        "v45_primary_candidate_minus_static": summary["all30_development_primary_candidate_minus_static"],
        "v45_candidate_minus_predictive": summary["all30_development_candidate_minus_predictive_final"],
        "v45_floor_reduction_vs_v43_percent": 100.0 * (1.0 - v45_floor / v43_floor),
        "v45_floor_reduction_vs_predictive_percent": 100.0 * (1.0 - v45_floor / predictive_floor),
        "v45_floor_reduction_vs_static_percent": 100.0 * (1.0 - v45_floor / static_floor),
        "v45_marginal_intervals_closed_over_v44": marginal_closed,
        "v45_marginal_interval_closure_percent_over_v44": marginal_percent,
        "major_remaining_issue": "FIXED_ASSOCIATION_BOUNDED_ACTION_SERVICEABILITY",
        "stopping_decision": contract["decision"],
        "fresh_holdout_seeds": contract["fresh_holdout_seeds"],
        "automatic_extra_seed_or_algorithm_tuning_authorized": False,
        "next_gate": contract["next_gate"],
    }
    write_json(out / "V45_FREEZE_VERDICT.json", metrics)

    claim_matrix = {
        "schema_version": 1,
        "hard_supported_claims": [
            "zero long-horizon EESS violations in the frozen development campaign",
            "zero short-horizon EESS violations in the frozen development campaign",
            "strict post-mode power compliance and bounded action-scope locality",
            "statistically positive development utility effect versus safe static and predictive baselines",
            "explicit fixed-association infeasibility reporting rather than tolerance or floor weakening",
        ],
        "feasibility_conditioned_claims": [
            "the unchanged user floor is enforced whenever the declared bounded action set is feasible",
            "residual user-floor shortfall is reported when fixed-association bounded-action feasibility fails",
        ],
        "forbidden_claims": [
            "universal zero user-floor violations",
            "information-exchange locality certification",
            "hardware calibration",
            "regulatory compliance",
            "fresh confirmation from seeds 44000-44029 after v4.5 adaptation",
        ],
        "major_fallbacks_not_silently_added": [
            "user reassignment or multi-connectivity",
            "preregistered serviceability-aware admission/defer",
        ],
    }
    write_json(out / "TWC_CLAIM_MATRIX.json", claim_matrix)

    with (out / "DEVELOPMENT_RESULT_TABLE.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        for key in (
            "v45_hard_gate_pass_seeds",
            "v45_bounded_scope_pass_seeds",
            "v45_floor_violation_user_seconds",
            "v45_residual_intervals",
            "v45_floor_reduction_vs_v43_percent",
            "v45_floor_reduction_vs_predictive_percent",
            "v45_floor_reduction_vs_static_percent",
            "v45_marginal_intervals_closed_over_v44",
            "v45_marginal_interval_closure_percent_over_v44",
        ):
            w.writerow([key, metrics[key]])

    print("V45_DEVELOPMENT_RETURN_BINDING=PASS")
    print("V45_DEVELOPMENT_SUMMARY_AUDIT=PASS")
    print("V45_HOLDOUT_JOB_PACKAGE_BINDING=PASS")
    print("V45_FREEZE_DECISION=PASS_STOP_ALGORITHM_TUNING")
    print(f"V45_MARGINAL_INTERVALS_CLOSED_OVER_V44={marginal_closed}")
    print(f"V45_MARGINAL_INTERVAL_CLOSURE_PERCENT={marginal_percent:.9f}")
    print("MAJOR_REMAINING_ISSUE=FIXED_ASSOCIATION_BOUNDED_ACTION_SERVICEABILITY")
    print("TWC_MANUSCRIPT_START_AUTHORIZED=YES")
    print("FRESH_HOLDOUT_AUTHORIZED=YES_EXACT_SEEDS_44030_44059_ONLY")
    print("AUTOMATIC_EXTRA_PROBES_AUTHORIZED=NO")
    print("NEXT_GATE=" + contract["next_gate"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
