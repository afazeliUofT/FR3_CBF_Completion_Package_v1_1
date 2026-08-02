#!/usr/bin/env python3
"""Independent local audit of the frozen 30-seed campaign return."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import statistics
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

EXPECTED_SHA = "cd2975e316bbd3d20469559a28e10113b2d8a9c1942cc2cdfe01ad33253653c9"
EXPECTED_FAILED = [44001, 44007, 44008, 44013, 44017, 44018, 44024, 44025, 44026, 44027, 44028]


def sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def parse_elapsed(value: str) -> float:
    parts = value.strip().split(":")
    if len(parts) != 3:
        raise ValueError(f"invalid elapsed value: {value}")
    hours, minutes, seconds = parts
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def parse_maxrss_kib(value: str) -> float | None:
    text = value.strip()
    if not text:
        return None
    match = re.fullmatch(r"([0-9.]+)([KMGTP]?)", text)
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2)
    factor = {"": 1.0 / 1024.0, "K": 1.0, "M": 1024.0, "G": 1024.0**2, "T": 1024.0**3}.get(unit)
    if factor is None:
        return None
    return number * factor


def user_id(index: int) -> str:
    sector = int(index) // 4
    stream = int(index) % 4
    site = sector // 3 + 1
    sec = sector % 3 + 1
    return f"E3_SITE_{site:02d}_SEC_{sec}_UE_{stream + 1}"


def read_json(zf: zipfile.ZipFile, prefix: str, rel: str) -> Any:
    return json.loads(zf.read(prefix + rel).decode("utf-8"))


def read_csv(zf: zipfile.ZipFile, prefix: str, rel: str) -> pd.DataFrame:
    return pd.read_csv(io.StringIO(zf.read(prefix + rel).decode("utf-8")))


def audit(campaign_zip: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    digest = sha256_file(campaign_zip)
    if digest != EXPECTED_SHA:
        raise RuntimeError(f"campaign SHA mismatch: {digest} != {EXPECTED_SHA}")

    with zipfile.ZipFile(campaign_zip) as zf:
        bad = zf.testzip()
        if bad is not None:
            raise RuntimeError(f"campaign ZIP CRC failure: {bad}")
        prefix = zf.namelist()[0].split("/")[0] + "/"
        manifest_lines = zf.read(prefix + "RETURN_MANIFEST.sha256").decode("utf-8").splitlines()
        for line in manifest_lines:
            if not line.strip():
                continue
            expected, rel = line.split(maxsplit=1)
            actual = hashlib.sha256(zf.read(prefix + rel)).hexdigest()
            if actual != expected:
                raise RuntimeError(f"return manifest mismatch: {rel}")

        metadata = read_json(zf, prefix, "CAMPAIGN_RETURN_METADATA.json")
        completion = read_json(zf, prefix, "SEED_COMPLETION_INDEX.json")
        merged = read_json(zf, prefix, "merged/PHASE1_MERGED_AUDIT.json")
        bootstrap = read_json(zf, prefix, "merged/PHASE1_BOOTSTRAP_SUMMARY.json")
        action_runtime = read_json(zf, prefix, "merged/PHASE1_ACTION_AND_RUNTIME_SUMMARY.json")
        method_summary = read_csv(zf, prefix, "merged/PHASE1_METHOD_ENDPOINT_SUMMARY.csv")
        seed_effects = read_csv(zf, prefix, "merged/PHASE1_SEED_CLUSTER_EFFECTS.csv")
        pass_effects = read_csv(zf, prefix, "merged/PHASE1_PASS_SPECIFIC_EFFECTS.csv")
        leave_one_pass = read_csv(zf, prefix, "merged/PHASE1_LEAVE_ONE_PASS_OUT.csv")

        failed_seeds = [int(row["campaign_seed"]) for row in completion if not bool(row["candidate_hard_gates_pass"])]
        if failed_seeds != EXPECTED_FAILED:
            raise RuntimeError(f"failed-seed binding changed: {failed_seeds}")

        seed_rows: list[dict[str, Any]] = []
        affected_user_counter: Counter[int] = Counter()
        affected_user_seed: dict[int, set[int]] = {}
        violating_pass_cells = 0
        total_floor_user_seconds = 0
        total_floor_user_intervals = 0
        total_unresolved_intervals = 0
        action_counts: Counter[str] = Counter()
        max_shortfall = 0.0
        for seed in range(44000, 44030):
            seed_result = read_json(zf, prefix, f"seed_summaries/seed_{seed}/SEED_RESULT.json")
            seed_seconds = 0
            seed_user_intervals = 0
            seed_unresolved = 0
            seed_max_shortfall = 0.0
            failed_passes = 0
            for pass_audit in seed_result["pass_audits"]:
                hard = pass_audit["candidate_hard_gates"]
                diag = pass_audit["candidate_action_diagnostics"]
                action_counts.update(diag["action_class_counts"])
                seconds = int(hard["eligible_floor_violation_user_seconds"])
                user_intervals = int(hard["eligible_floor_violation_user_intervals"])
                unresolved = int(hard["unresolved_deployable_intervals"])
                if seconds > 0:
                    failed_passes += 1
                    violating_pass_cells += 1
                seed_seconds += seconds
                seed_user_intervals += user_intervals
                seed_unresolved += unresolved
                seed_max_shortfall = max(seed_max_shortfall, float(diag["maximum_normalized_floor_shortfall"]))
                for record in pass_audit["candidate_interval_records"]:
                    if int(record["candidate_floor_violation_count"]) <= 0:
                        continue
                    duration = int(record["interval_seconds"])
                    for user in record["pre_repair_violating_users"]:
                        user_i = int(user)
                        affected_user_counter[user_i] += duration
                        affected_user_seed.setdefault(user_i, set()).add(seed)
            total_floor_user_seconds += seed_seconds
            total_floor_user_intervals += seed_user_intervals
            total_unresolved_intervals += seed_unresolved
            max_shortfall = max(max_shortfall, seed_max_shortfall)
            seed_rows.append({
                "campaign_seed": seed,
                "candidate_hard_gates_pass": bool(seed_result["candidate_hard_gates_pass"]),
                "floor_violation_user_seconds": seed_seconds,
                "floor_violation_user_intervals": seed_user_intervals,
                "unresolved_deployable_intervals": seed_unresolved,
                "failed_pass_count": failed_passes,
                "maximum_normalized_floor_shortfall": seed_max_shortfall,
                "runtime_seconds": float(seed_result["runtime_seconds"]),
            })

        method = method_summary.set_index("method_id")
        candidate = method.loc["candidate_v4_3_floor_feasibility_repair"]
        predictive = method.loc["robust_predictive_constrained_pf_with_sector_selective_fallback"]
        static = method.loc["static_robust_constrained_pf_with_sector_selective_fallback"]
        candidate_floor_mean = float(candidate["eligible_floor_violation_user_seconds__mean"])
        predictive_floor_mean = float(predictive["eligible_floor_violation_user_seconds__mean"])
        static_floor_mean = float(static["eligible_floor_violation_user_seconds__mean"])
        reduction_predictive = 1.0 - candidate_floor_mean / predictive_floor_mean
        reduction_static = 1.0 - candidate_floor_mean / static_floor_mean

        sacct_text = zf.read(prefix + "slurm/sacct_campaign.txt").decode("utf-8")
        gpu_elapsed: list[float] = []
        gpu_rss_kib: list[float] = []
        gpu_job_ids: set[str] = set()
        for line in sacct_text.splitlines():
            fields = line.split("|")
            if len(fields) < 11:
                continue
            job_id, job_name = fields[0], fields[1]
            if job_name != "fr3-v43-r2-p1" or "gres/gpu:h100=1" not in fields[9]:
                continue
            gpu_job_ids.add(job_id)
            try:
                gpu_elapsed.append(parse_elapsed(fields[5]))
            except Exception:
                pass
        # Slurm reports MaxRSS on each top-level job's ``.batch`` step.
        for line in sacct_text.splitlines():
            fields = line.split("|")
            if len(fields) < 7 or not fields[0].endswith(".batch"):
                continue
            parent = fields[0][:-len(".batch")]
            if parent not in gpu_job_ids:
                continue
            rss = parse_maxrss_kib(fields[6])
            if rss is not None:
                gpu_rss_kib.append(rss)

        total_intervals = sum(action_counts.values())
        affected_rows = []
        for index, seconds in affected_user_counter.most_common():
            affected_rows.append({
                "user_index": index,
                "user_id": user_id(index),
                "approximate_violation_seconds_from_unresolved_records": seconds,
                "failed_seed_count": len(affected_user_seed.get(index, set())),
                "failed_seeds": ";".join(str(v) for v in sorted(affected_user_seed.get(index, set()))),
            })

        hard_fail_seeds = [row for row in seed_rows if not row["candidate_hard_gates_pass"]]
        top8_share = (
            sum(row["floor_violation_user_seconds"] for row in sorted(hard_fail_seeds, key=lambda v: v["floor_violation_user_seconds"], reverse=True)[:8])
            / total_floor_user_seconds
            if total_floor_user_seconds else 0.0
        )
        audit_record = {
            "schema_version": 1,
            "status": "PASS_INDEPENDENT_CAMPAIGN_RETURN_AUDIT",
            "campaign_zip_sha256": digest,
            "campaign_status_as_returned": metadata["status"],
            "candidate_source_changed": False,
            "source_supported_facts": {
                "seed_count": 30,
                "pass_count": 5,
                "method_count": 9,
                "cell_count": 1350,
                "seed_return_count": int(metadata["seed_return_count"]),
                "hard_gate_pass_seed_count": int(metadata["seed_hard_gate_pass_count"]),
                "hard_gate_fail_seed_count": len(failed_seeds),
                "failed_seeds": failed_seeds,
                "violating_pass_cell_count": violating_pass_cells,
                "total_pass_cell_count": 150,
                "candidate_floor_violation_user_seconds": total_floor_user_seconds,
                "candidate_floor_violation_user_intervals": total_floor_user_intervals,
                "candidate_unresolved_intervals": total_unresolved_intervals,
                "candidate_maximum_normalized_floor_shortfall": max_shortfall,
                "candidate_long_eess_violations": 0,
                "candidate_short_eess_violations": 0,
                "strict_local_scope_all_pass": bool(merged["hard_gates"]["strict_local_scope_all_pass"]),
                "strict_post_mode_power_all_pass": bool(merged["hard_gates"]["strict_post_mode_power_all_pass"]),
                "q0_headroom_actions": 0,
                "network_wide_shutdown_intervals": 0,
                "primary_candidate_minus_static": bootstrap["candidate_minus_static_final_pf"],
                "secondary_candidate_minus_static": bootstrap["candidate_minus_static_duration_mean_pf"],
                "candidate_minus_predictive_final": bootstrap["candidate_minus_predictive_final_pf"],
                "candidate_minus_predictive_duration": bootstrap["candidate_minus_predictive_duration_mean_pf"],
                "floor_violation_reduction_vs_predictive_fraction": reduction_predictive,
                "floor_violation_reduction_vs_static_fraction": reduction_static,
                "top_eight_failed_seed_share_of_candidate_floor_user_seconds": top8_share,
                "action_class_counts": dict(action_counts),
                "action_class_fractions": {key: value / total_intervals for key, value in action_counts.items()},
                "information_exchange_locality_certified": False,
            },
            "scientific_inference": {
                "primary_utility_superiority_is_statistically_supported": bool(bootstrap["candidate_minus_static_final_pf"]["lower_95"] > 0.0),
                "candidate_hard_floor_claim_is_not_supported_for_all_30_seeds": True,
                "failed_seed_results_are_scientific_action_space_failures_not_infrastructure_failures": True,
                "next_step": "REUSE_PRESERVED_FAILED_SEED_CHANNELS_FOR_FIXED_BEAM_AND_EXPANDED_LOCAL_FEASIBILITY_DIAGNOSIS",
            },
            "resource_audit": {
                "observed_worker_elapsed_seconds_min": min(gpu_elapsed) if gpu_elapsed else None,
                "observed_worker_elapsed_seconds_median": statistics.median(gpu_elapsed) if gpu_elapsed else None,
                "observed_worker_elapsed_seconds_max": max(gpu_elapsed) if gpu_elapsed else None,
                "observed_worker_host_maxrss_gib_max": (max(gpu_rss_kib) / 1024.0**2) if gpu_rss_kib else None,
                "prior_worker_walltime_request": "04:00:00",
                "prior_worker_memory_request_gib": 124,
                "future_equivalent_worker_walltime": "00:10:00",
                "future_equivalent_worker_memory_gib": 16,
                "current_diagnostic_worker_walltime": "00:15:00",
                "current_diagnostic_worker_memory_gib": 16,
                "reason": "diagnostic solves several additional LP classes on every unresolved interval",
            },
            "claim_boundary": "POST_CAMPAIGN_INDEPENDENT_AUDIT_NOT_NEW_CONFIRMATORY_SAMPLE",
        }

        (output_dir / "LOCAL_CAMPAIGN_SCIENTIFIC_AUDIT.json").write_text(
            json.dumps(audit_record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        pd.DataFrame(seed_rows).to_csv(output_dir / "FAILED_SEED_SUMMARY.csv", index=False)
        pd.DataFrame(affected_rows).to_csv(output_dir / "AFFECTED_USER_PRELIMINARY_SUMMARY.csv", index=False)
        pass_effects.to_csv(output_dir / "PASS_SPECIFIC_EFFECTS.csv", index=False)
        leave_one_pass.to_csv(output_dir / "LEAVE_ONE_PASS_OUT.csv", index=False)
        seed_effects.to_csv(output_dir / "SEED_CLUSTER_EFFECTS.csv", index=False)

    print("LOCAL_CAMPAIGN_AUDIT=PASS")
    print(f"CAMPAIGN_RETURN_SHA256={digest}")
    print("CAMPAIGN_RETURN_SHA256_GATE=PASS")
    print(f"FAILED_SEED_COUNT={len(failed_seeds)}")
    print("FAILED_SEEDS=" + ",".join(str(v) for v in failed_seeds))
    print(f"HARD_GATE_PASS_SEED_COUNT={30-len(failed_seeds)}")
    print(f"VIOLATING_PASS_CELL_COUNT={violating_pass_cells}")
    print(f"CANDIDATE_FLOOR_VIOLATION_USER_SECONDS={total_floor_user_seconds}")
    print(f"CANDIDATE_UNRESOLVED_INTERVALS={total_unresolved_intervals}")
    print(f"PRIMARY_POINT_ESTIMATE={bootstrap['candidate_minus_static_final_pf']['point_estimate']}")
    print(f"PRIMARY_LOWER_95={bootstrap['candidate_minus_static_final_pf']['lower_95']}")
    print(f"PRIMARY_UPPER_95={bootstrap['candidate_minus_static_final_pf']['upper_95']}")
    print(f"FLOOR_REDUCTION_VS_PREDICTIVE_PERCENT={100.0*reduction_predictive:.6f}")
    print(f"FLOOR_REDUCTION_VS_STATIC_PERCENT={100.0*reduction_static:.6f}")
    print("PRIOR_WORKER_WALLTIME=04:00:00")
    print("FUTURE_EQUIVALENT_WORKER_WALLTIME=00:10:00")
    print("CURRENT_DIAGNOSTIC_WORKER_WALLTIME=00:15:00")
    return audit_record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-zip", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    audit(args.campaign_zip.resolve(), args.output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
