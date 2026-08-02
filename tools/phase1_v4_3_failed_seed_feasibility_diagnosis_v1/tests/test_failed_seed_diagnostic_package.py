from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FAILED = [44001, 44007, 44008, 44013, 44017, 44018, 44024, 44025, 44026, 44027, 44028]


def load_module(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def file_sha(path: Path) -> str:
    value = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def test_exact_campaign_audit_and_resource_profile(tmp_path: Path) -> None:
    audit_module = load_module("campaign_audit", "scripts/audit_campaign_return.py")
    campaign = ROOT / "immutable_bindings/FR3_RORQUAL_V4_3_R2_30SEED_CAMPAIGN_18145937.zip"
    record = audit_module.audit(campaign, tmp_path)
    facts = record["source_supported_facts"]
    resource = record["resource_audit"]
    assert facts["failed_seeds"] == FAILED
    assert facts["hard_gate_pass_seed_count"] == 19
    assert facts["candidate_floor_violation_user_seconds"] == 19994
    assert facts["candidate_floor_violation_user_intervals"] == 4016
    assert facts["candidate_unresolved_intervals"] == 1736
    assert facts["primary_candidate_minus_static"]["lower_95"] > 0.0
    assert facts["candidate_long_eess_violations"] == 0
    assert facts["candidate_short_eess_violations"] == 0
    assert resource["observed_worker_elapsed_seconds_max"] == 180.0
    assert 2.2 < resource["observed_worker_host_maxrss_gib_max"] < 2.4
    assert resource["future_equivalent_worker_walltime"] == "00:10:00"
    assert resource["current_diagnostic_worker_walltime"] == "00:15:00"


def test_immutable_bindings() -> None:
    campaign = ROOT / "immutable_bindings/FR3_RORQUAL_V4_3_R2_30SEED_CAMPAIGN_18145937.zip"
    job = ROOT / "immutable_bindings/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2.zip"
    assert file_sha(campaign) == "cd2975e316bbd3d20469559a28e10113b2d8a9c1942cc2cdfe01ad33253653c9"
    assert file_sha(job) == "c106fa6441b15873d0d2d9b29d636434625edcd58f4033a4700589cb91e19e82"


def test_resource_contract_is_bounded_and_cpu_only() -> None:
    contract = json.loads((ROOT / "config/DIAGNOSTIC_CONTRACT.json").read_text())
    resource = contract["resource_contract"]
    assert resource["worker_walltime"] == "00:15:00"
    assert resource["merge_walltime"] == "00:05:00"
    assert resource["worker_memory_gib"] == 16
    assert resource["gpu_requested"] is False
    assert resource["channel_regeneration"] is False
    remote = (ROOT / "wrappers/REMOTE_ORCHESTRATE_FAILED_SEED_DIAGNOSIS.sh").read_text()
    assert "#SBATCH --time=00:15:00" in remote
    assert "#SBATCH --time=00:05:00" in remote
    assert "#SBATCH --mem=16G" in remote
    assert "#SBATCH --gres" not in remote


def test_exact_stream_audit_enforces_strict_post_mode_power() -> None:
    module = load_module("seed_diag", "scripts/diagnose_failed_seed.py")

    class DummyRepair:
        @staticmethod
        def exact_audit(**_kwargs):
            return SimpleNamespace(
                floor_violation_count=0,
                long_violation_seconds=0,
                short_violation_seconds=0,
                maximum_normalized_floor_shortfall=0.0,
                minimum_active_eligible_floor_ratio=1.1,
                maximum_long_ratio=0.8,
                maximum_short_ratio=0.9,
            )

    state = SimpleNamespace(
        other_weighted_rate=np.zeros(1),
        active_user=np.ones(1, dtype=bool),
    )
    kwargs = {
        "state": state,
        "eligible_user": np.ones(1, dtype=bool),
        "floors": np.ones(1),
        "serving_bs": np.zeros(1, dtype=np.int64),
        "serving_stream": np.zeros(1, dtype=np.int64),
        "protected_noise_w": 1.0,
        "protected_weight": 1.0,
        "long_kappa_second_sector": np.ones((1, 1)),
        "short_kappa_second_sector": np.ones((1, 1)),
        "long_allowance_second": np.ones(1),
        "short_allowance_second": np.ones(1),
        "coupling_uplift_db": 0.0,
    }
    system = {
        "gain": np.ones((1, 1, 2)),
        "leakage": np.ones((1, 2)),
        "stream_power": np.ones((1, 2)),
        "baseline_sector": np.array([0.5]),
    }
    passed = module.exact_stream_audit(
        DummyRepair, np.array([0.5, 0.5]), kwargs, system
    )
    failed = module.exact_stream_audit(
        DummyRepair, np.array([1.0, 1.0]), kwargs, system
    )
    assert passed["exact_feasible"] is True
    assert passed["maximum_strict_post_mode_power_ratio"] == 1.0
    assert failed["exact_feasible"] is False
    assert failed["maximum_strict_post_mode_power_ratio"] == 2.0


def make_merge_fixture(root: Path, mode: str) -> tuple[Path, Path]:
    task_root = root / "tasks"
    task_root.mkdir(parents=True)
    for index, seed in enumerate(FAILED):
        seed_root = task_root / f"seed_{seed}"
        seed_root.mkdir()
        fields = {
            "campaign_seed": seed,
            "channel_reused": True,
            "original_unresolved_interval_count": 1,
            "expanded_local_certified_interval_count": 1,
            "expanded_local_boundary_interval_count": 0,
            "strict_global_only_interval_count": 0,
            "solver_uncertified_interval_count": 0,
            "boundary_only_interval_count": 0,
            "fixed_beam_single_user_infeasible_interval_count": 0,
            "fixed_beam_joint_infeasible_interval_count": 0,
            "current_load_serviceability_mismatch_interval_count": 0,
        }
        classification = "EXPANDED_LOCAL_HYBRID_K4_FEASIBLE"
        if index == 0 and mode == "scheduling":
            fields["expanded_local_certified_interval_count"] = 0
            fields["fixed_beam_single_user_infeasible_interval_count"] = 1
            classification = "FIXED_Q_FIXED_BEAM_SINGLE_USER_INFEASIBLE"
        elif index == 0 and mode == "uncertified":
            fields["expanded_local_certified_interval_count"] = 0
            fields["solver_uncertified_interval_count"] = 1
            classification = "STRICT_GLOBAL_FIXED_BEAM_SOLVER_UNCERTIFIED"
        (seed_root / "FAILED_SEED_DIAGNOSIS.json").write_text(
            json.dumps(fields), encoding="utf-8"
        )
        detail = [{
            "classification": classification,
            "pass_slot": 0,
            "interval_index": index,
            "interval_seconds": 5,
            "original_candidate_floor_violation_count": 1,
            "current_load_serviceability_mismatch_present": False,
            "selected_expanded_local_witness": (
                None if not classification.startswith("EXPANDED_LOCAL") else {
                    "scope": {
                        "action_class": "EXPANDED_LOCAL_HYBRID",
                        "external_per_user": 4,
                        "mutable_sector_count": 5,
                    }
                }
            ),
        }]
        (seed_root / "INTERVAL_FEASIBILITY_DIAGNOSIS.json").write_text(
            json.dumps(detail), encoding="utf-8"
        )
        pd.DataFrame([{
            "campaign_seed": seed,
            "user_index": 0,
            "user_id": "E3_SITE_01_SEC_1_UE_1",
            "interval_index": index,
            "current_load_nominal_total_rate_bps_hz": 1.0,
            "optimistic_total_rate_bps_hz": 2.0,
            "floor_bps_hz": 0.9,
            "current_load_serviceability_mismatch": False,
        }]).to_csv(seed_root / "AFFECTED_USER_DIAGNOSIS.csv", index=False)
    audit = root / "audit.json"
    audit.write_text(json.dumps({
        "source_supported_facts": {"candidate_unresolved_intervals": 11},
        "resource_audit": {"observed_worker_elapsed_seconds_max": 180.0},
    }), encoding="utf-8")
    return task_root, audit


def run_merge(tmp_path: Path, mode: str) -> dict:
    task_root, audit = make_merge_fixture(tmp_path, mode)
    output = tmp_path / "merged"
    subprocess.run([
        "python3", str(ROOT / "scripts/merge_failed_seed_diagnostics.py"),
        "--task-root", str(task_root),
        "--campaign-audit", str(audit),
        "--output-dir", str(output),
    ], check=True, capture_output=True, text=True)
    return json.loads((output / "NEXT_REPAIR_DECISION.json").read_text())


def test_merge_selects_adaptive_local_repair(tmp_path: Path) -> None:
    record = run_merge(tmp_path, "adaptive")
    assert record["next_repair_decision"] == "ADAPTIVE_LOCAL_FIXED_BEAM_REPAIR"


def test_merge_selects_scheduling_for_fixed_beam_infeasibility(tmp_path: Path) -> None:
    record = run_merge(tmp_path, "scheduling")
    assert record["next_repair_decision"] == "PROTECTED_SUBBAND_SCHEDULING_REASSIGNMENT_REQUIRED"


def test_merge_refuses_physical_claim_when_solver_uncertified(tmp_path: Path) -> None:
    record = run_merge(tmp_path, "uncertified")
    assert record["next_repair_decision"] == "SOLVER_CERTIFICATE_REFINEMENT_REQUIRED"


def build_synthetic_return(tmp_path: Path, complete: bool) -> Path:
    root = tmp_path / "FR3_RORQUAL_V4_3_FAILED_SEED_DIAGNOSIS_123"
    root.mkdir()
    (root / "RETURN_STATUS.json").write_text(json.dumps({
        "schema_version": 1,
        "status": "PASS_COMPLETE_DIAGNOSIS_RETURN" if complete else "EMERGENCY_PARTIAL_RETURN",
        "merge_exit_code": 0 if complete else 42,
    }), encoding="utf-8")
    for seed in FAILED:
        seed_dir = root / "seed_diagnostics" / f"seed_{seed}"
        seed_dir.mkdir(parents=True)
        (seed_dir / "TASK_STATUS.json").write_text("{}\n", encoding="utf-8")
    if complete:
        merged = root / "merged"
        merged.mkdir()
        (merged / "NEXT_REPAIR_DECISION.json").write_text(json.dumps({
            "next_repair_decision": "ADAPTIVE_LOCAL_FIXED_BEAM_REPAIR",
            "next_gate": "IMPLEMENT_V4_4_ADAPTIVE_LOCAL_REPAIR_AND_TARGETED_11_SEED_RERUN",
            "diagnosed_unresolved_interval_count": 1736,
        }), encoding="utf-8")
    files = sorted(p for p in root.rglob("*") if p.is_file())
    lines = []
    for path in files:
        rel = path.relative_to(root)
        lines.append(f"{file_sha(path)}  {rel.as_posix()}")
    (root / "RETURN_MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    archive = tmp_path / (root.name + ".zip")
    import zipfile
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            zf.write(path, f"{root.name}/{path.relative_to(root).as_posix()}")
    return archive


def test_return_verifier_accepts_complete_and_preserves_partial(tmp_path: Path) -> None:
    complete_dir = tmp_path / "complete"
    complete_dir.mkdir()
    complete = build_synthetic_return(complete_dir, True)
    result = subprocess.run([
        "python3", str(ROOT / "scripts/verify_diagnostic_return.py"),
        "--return-zip", str(complete),
    ], capture_output=True, text=True)
    assert result.returncode == 0
    assert "DIAGNOSTIC_RETURN_COMPLETENESS=COMPLETE" in result.stdout

    partial_dir = tmp_path / "partial"
    partial_dir.mkdir()
    partial = build_synthetic_return(partial_dir, False)
    result = subprocess.run([
        "python3", str(ROOT / "scripts/verify_diagnostic_return.py"),
        "--return-zip", str(partial),
    ], capture_output=True, text=True)
    assert result.returncode == 42
    assert "PARTIAL_REVIEW_REQUIRED" in result.stdout
