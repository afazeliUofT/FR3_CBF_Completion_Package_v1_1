from __future__ import annotations

import inspect
import json
from pathlib import Path
import tempfile
import zipfile

import numpy as np

from fr3_cbf.protected_subband_scheduler import (
    SLOTS_PER_SECOND,
    generate_schedule_modes,
    schedule_interval,
)
from fr3_cbf.candidate_v4_4_scheduling_campaign import run_candidate_v4_4


def make_same_sector_problem(floor: float = 1.5) -> dict[str, object]:
    # Two users share one sector and strongly interfere when served together.
    # A 50/50 integer slot schedule of the two fixed RZF columns closes floors.
    gain = np.zeros((2, 1, 2), dtype=np.float64)
    gain[0, 0, 0] = 10.0
    gain[0, 0, 1] = 10.0
    gain[1, 0, 0] = 10.0
    gain[1, 0, 1] = 10.0
    return {
        "gain_user_sector_stream": gain,
        "baseline_stream_scale": np.ones((1, 2), dtype=np.float64),
        "other_weighted_rate": np.zeros(2, dtype=np.float64),
        "active_user": np.ones(2, dtype=bool),
        "eligible_user": np.ones(2, dtype=bool),
        "floors": np.full(2, floor, dtype=np.float64),
        "serving_bs": np.zeros(2, dtype=np.int64),
        "serving_stream": np.array([0, 1], dtype=np.int64),
        "protected_noise_w": 1.0,
        "protected_weight": 1.0,
        "long_kappa_second_sector": np.ones((2, 1), dtype=np.float64),
        "short_kappa_second_sector": np.ones((2, 1), dtype=np.float64),
        "leakage_sector_stream": np.full((1, 2), 0.01, dtype=np.float64),
        "long_allowance_second": np.full(2, 10.0, dtype=np.float64),
        "short_allowance_second": np.full(2, 10.0, dtype=np.float64),
        "coupling_uplift_db": 0.0,
        "actual_stream_power": np.ones((1, 2), dtype=np.float64),
        "violating_users": (0, 1),
    }


def test_same_sector_conflict_is_closed_by_physical_slot_schedule() -> None:
    outcome = schedule_interval(**make_same_sector_problem())
    assert outcome.feasible
    assert outcome.status == "DEPLOYABLE_SCHEDULING_FEASIBLE"
    assert outcome.floor_violation_count == 0
    assert outcome.long_violation_seconds == 0
    assert outcome.short_violation_seconds == 0
    assert outcome.slot_count_per_second == 2000
    assert outcome.slot_counts is not None
    assert int(outcome.slot_counts.sum()) == SLOTS_PER_SECOND
    assert outcome.nonzero_mode_count >= 2
    assert outcome.maximum_post_mode_power_ratio is not None
    assert outcome.maximum_post_mode_power_ratio <= 1.0 + 1e-10
    assert outcome.minimum_active_eligible_floor_ratio is not None
    assert outcome.minimum_active_eligible_floor_ratio >= 1.0


def test_impossible_time_share_is_not_certified() -> None:
    outcome = schedule_interval(**make_same_sector_problem(floor=2.0))
    assert not outcome.feasible
    assert outcome.status in {
        "CONTINUOUS_SCHEDULING_INFEASIBLE",
        "CONTINUOUS_FEASIBLE_BUT_SLOT_QUANTIZATION_UNCERTIFIED",
        "QUANTIZED_SCHEDULE_EXACT_AUDIT_FAILED",
    }


def test_scheduler_requires_a_violating_user() -> None:
    args = make_same_sector_problem()
    args["violating_users"] = ()
    outcome = schedule_interval(**args)
    assert not outcome.feasible
    assert outcome.status == "NO_VIOLATING_USER"
    assert outcome.mode_count == 1


def test_sparse_external_guard_is_used_only_after_local_change() -> None:
    # User 0 is served by sector 0. Sector 1 is a dominant interferer. The
    # baseline serving coefficient is 0.5, so the singleton serving mode is a
    # genuine local change and activates the fixed total guard set.
    gain = np.zeros((1, 2, 1), dtype=np.float64)
    gain[0, 0, 0] = 1.0
    gain[0, 1, 0] = 10.0
    outcome = schedule_interval(
        gain_user_sector_stream=gain,
        baseline_stream_scale=np.array([[0.5], [1.0]], dtype=np.float64),
        other_weighted_rate=np.zeros(1, dtype=np.float64),
        active_user=np.ones(1, dtype=bool),
        eligible_user=np.ones(1, dtype=bool),
        floors=np.array([0.8], dtype=np.float64),
        serving_bs=np.array([0], dtype=np.int64),
        serving_stream=np.array([0], dtype=np.int64),
        protected_noise_w=1.0,
        protected_weight=1.0,
        long_kappa_second_sector=np.ones((2, 2), dtype=np.float64),
        short_kappa_second_sector=np.ones((2, 2), dtype=np.float64),
        leakage_sector_stream=np.full((2, 1), 0.001, dtype=np.float64),
        long_allowance_second=np.full(2, 10.0, dtype=np.float64),
        short_allowance_second=np.full(2, 10.0, dtype=np.float64),
        coupling_uplift_db=0.0,
        actual_stream_power=np.ones((2, 1), dtype=np.float64),
        violating_users=(0,),
    )
    assert outcome.feasible
    assert outcome.guard_sector_limit == 2
    assert outcome.guard_sector_union == (1,)
    assert outcome.maximum_guard_sector_count == 1
    assert set(outcome.mutable_sectors) == {0, 1}
    assert outcome.floor_violation_count == 0


def test_mode_generation_has_explicit_bounded_union() -> None:
    gain = np.zeros((4, 8, 4), dtype=np.float64)
    serving = np.arange(4, dtype=np.int64)
    stream = np.zeros(4, dtype=np.int64)
    for user in range(4):
        gain[user, user, 0] = 1.0
        gain[user, 4:, 0] = np.array([4.0, 3.0, 2.0, 1.0])
    modes, critical = generate_schedule_modes(
        gain_user_sector_stream=gain,
        baseline_stream_scale=np.ones((8, 4), dtype=np.float64),
        active_user=np.ones(4, dtype=bool),
        serving_bs=serving,
        serving_stream=stream,
        violating_users=(0, 1, 2, 3),
        guard_sector_limit=4,
    )
    assert critical == (0, 1, 2, 3)
    assert len(modes) <= 512
    assert all(len(mode.guard_sectors) <= 4 for mode in modes)
    union = set().union(*(set(mode.guard_sectors) for mode in modes))
    assert len(union) <= 4


def test_diagnosis_binding_and_decision(package_root: Path) -> None:
    archive = (
        package_root
        / "immutable_bindings/FR3_RORQUAL_V4_3_FAILED_SEED_DIAGNOSIS_18150465.zip"
    )
    with zipfile.ZipFile(archive) as zf:
        assert zf.testzip() is None
        root = zf.namelist()[0].split("/", 1)[0]
        decision = json.loads(
            zf.read(f"{root}/merged/NEXT_REPAIR_DECISION.json")
        )
    assert (
        decision["next_repair_decision"]
        == "PROTECTED_SUBBAND_SCHEDULING_REASSIGNMENT_REQUIRED"
    )
    assert decision["diagnosed_unresolved_interval_count"] == 1736
    assert decision["fixed_beam_joint_global_infeasible_interval_count"] == 1284
    assert decision["fixed_beam_single_user_infeasible_interval_count"] == 0


def test_immutable_job_package_binding_and_signature(package_root: Path) -> None:
    archive = (
        package_root
        / "immutable_bindings/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2.zip"
    )
    with zipfile.ZipFile(archive) as zf:
        assert zf.testzip() is None
        contract = json.loads(zf.read("JOB_PACKAGE_CONTRACT.json"))
        v43_source = zf.read(
            "src/fr3_cbf/candidate_v4_3_campaign.py"
        ).decode("utf-8")
    assert (
        contract["package_id"]
        == "8473d5504e69347a69a536c43dcae35bec9519a90bc55de3a0712f9e0fb97889"
    )
    # Parse the immutable v4.3 function without importing a second fr3_cbf tree.
    import ast

    module = ast.parse(v43_source)
    function = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "run_candidate_v4_3"
    )
    immutable_names = [argument.arg for argument in function.args.kwonlyargs]
    v44_names = list(inspect.signature(run_candidate_v4_4).parameters)
    assert immutable_names == v44_names


def test_contract_matches_physical_slot_and_bounded_guard_scope(
    package_root: Path,
) -> None:
    contract = json.loads(
        (package_root / "config/V44_SCHEDULING_DEVELOPMENT_CONTRACT.json")
        .read_text(encoding="utf-8")
    )
    action = contract["scheduling_action"]
    assert action["slot_duration_seconds"] == 0.0005
    assert action["slots_per_physical_second"] == 2000
    assert action["maximum_deployable_total_guard_sectors"] == 4
    assert action["diagnostic_total_guard_sectors"] == 8
    assert action["mode_commands_frozen"] is True
    assert action["rzf_directions_frozen"] is True
    assert action["floor_comparison_tolerance"] == 1e-12
    assert action["eess_verification_tolerance"] == 1e-10


def _run_script(script: Path, *arguments: str) -> None:
    import os
    import subprocess
    import sys

    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, str(script), *arguments],
        check=False,
        text=True,
        capture_output=True,
        env=environment,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"script failed ({completed.returncode}): {script}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )


def test_complete_and_partial_return_packaging(
    package_root: Path,
    tmp_path: Path,
) -> None:
    import hashlib

    package_script = package_root / "scripts/package_v44_scheduling_return.py"
    verify_script = package_root / "scripts/verify_v44_scheduling_return.py"
    expected_seeds = [
        44001, 44007, 44008, 44013, 44017, 44018,
        44024, 44025, 44026, 44027, 44028,
    ]

    for complete in (True, False):
        run_root = tmp_path / ("complete" if complete else "partial")
        output_dir = run_root / "return"
        seeds = expected_seeds if complete else expected_seeds[:3]
        for seed in seeds:
            result = run_root / "tasks" / f"seed_{seed}" / "result"
            result.mkdir(parents=True)
            (result / "V44_SCHEDULING_SEED_RESULT.json").write_text(
                json.dumps({"campaign_seed": seed, "status": "PASS"}) + "\n",
                encoding="utf-8",
            )
            (result / "CELL_SUMMARY.csv").write_text(
                "method_id,pass_slot\n"
                "candidate_v4_4_floor_first_protected_subband_scheduling,0\n",
                encoding="utf-8",
            )
        if complete:
            merged = run_root / "merged"
            merged.mkdir(parents=True)
            (merged / "V44_SCHEDULING_DEVELOPMENT_SUMMARY.json").write_text(
                json.dumps({
                    "status": "PASS_V4_4_FLOOR_FIRST_PROTECTED_SUBBAND_SCHEDULING_DEVELOPMENT",
                    "next_repair_decision": "FREEZE_V4_4_BEGIN_TWC_DRAFT_AND_RUN_FRESH_HOLDOUT_IN_PARALLEL",
                    "next_gate": "FREEZE_V4_4_START_13_PAGE_TWC_DRAFT_AND_RUN_FRESH_HOLDOUT_44030_44059",
                }) + "\n",
                encoding="utf-8",
            )
        _run_script(
            package_script,
            "--run-root", str(run_root),
            "--package-root", str(package_root),
            "--array-job-id", "12345" if complete else "12346",
            "--merge-job-id", "22345" if complete else "22346",
            "--output-dir", str(output_dir),
        )
        archive = next(output_dir.glob("*.zip"))
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        verification = run_root / "verification.json"
        _run_script(
            verify_script,
            "--return-zip", str(archive),
            "--expected-sha256", digest,
            "--output-json", str(verification),
        )
        record = json.loads(verification.read_text(encoding="utf-8"))
        if complete:
            assert record["return_completeness"] == "COMPLETE"
            assert record["scientific_pass"] is True
        else:
            assert record["return_completeness"] == "PARTIAL"
            assert record["scientific_pass"] is False


def test_synthetic_merge_contract_and_bootstrap(
    package_root: Path,
    tmp_path: Path,
) -> None:
    import subprocess
    import sys

    failed_seeds = [
        44001, 44007, 44008, 44013, 44017, 44018,
        44024, 44025, 44026, 44027, 44028,
    ]
    all_seeds = range(44000, 44030)
    new_candidate = "candidate_v4_4_floor_first_protected_subband_scheduling"
    old_candidate = "candidate_v4_3_floor_feasibility_repair"
    static = "static_robust_constrained_pf_with_sector_selective_fallback"
    predictive = "robust_predictive_constrained_pf_with_sector_selective_fallback"
    task_root = tmp_path / "tasks"
    campaign_root = tmp_path / "campaign"
    diagnosis = tmp_path / "diagnosis.json"
    output = tmp_path / "merged"
    diagnosis.write_text(json.dumps({
        "status": "PASS_IMMUTABLE_FAILED_SEED_DIAGNOSIS_AUDIT",
        "diagnosed_unresolved_interval_count": 1736,
    }) + "\n", encoding="utf-8")

    unresolved_by_seed = {seed: 0 for seed in failed_seeds}
    unresolved_by_seed[failed_seeds[0]] = 1736
    for seed in all_seeds:
        result = campaign_root / "results" / f"seed_{seed}" / "result"
        result.mkdir(parents=True)
        rows = []
        for pass_slot in range(5):
            for method, final, duration in (
                (old_candidate, 1.1, 1.0),
                (static, 1.0, 0.9),
                (predictive, 1.05, 0.95),
            ):
                rows.append({
                    "method_id": method,
                    "pass_slot": pass_slot,
                    "final_moving_pf_utility": final,
                    "duration_weighted_mean_moving_pf_utility": duration,
                })
        import pandas as pd
        pd.DataFrame(rows).to_csv(result / "CELL_SUMMARY.csv", index=False)

        if seed in failed_seeds:
            new_result = task_root / f"seed_{seed}" / "result"
            new_result.mkdir(parents=True)
            pd.DataFrame([
                {
                    "method_id": new_candidate,
                    "pass_slot": pass_slot,
                    "final_moving_pf_utility": 1.2,
                    "duration_weighted_mean_moving_pf_utility": 1.1,
                }
                for pass_slot in range(5)
            ]).to_csv(new_result / "CELL_SUMMARY.csv", index=False)
            unresolved = unresolved_by_seed[seed]
            (new_result / "V44_SCHEDULING_SEED_RESULT.json").write_text(
                json.dumps({
                    "campaign_seed": seed,
                    "candidate_hard_gates_pass": True,
                    "bounded_schedule_scope_pass": True,
                    "original_v4_3_unresolved_intervals": unresolved,
                    "scheduling_success_intervals": unresolved,
                    "scheduling_failure_intervals": 0,
                    "diagnostic_g8_scheduling_feasible_intervals": 0,
                    "schedule_guard_limit_counts": {"2": unresolved} if unresolved else {},
                    "maximum_schedule_guard_sector_limit": 2 if unresolved else 0,
                    "maximum_schedule_guard_sector_count": 2 if unresolved else 0,
                    "maximum_schedule_critical_sector_count": 4 if unresolved else 0,
                    "maximum_schedule_mutable_sector_count": 6 if unresolved else 0,
                    "maximum_schedule_mode_count": 64 if unresolved else 0,
                    "maximum_schedule_nonzero_mode_count": 5 if unresolved else 0,
                    "maximum_protected_subband_scheduled_fraction": 0.42 if unresolved else 0.0,
                    "maximum_schedule_solver_seconds": 0.1,
                    "candidate_floor_violation_user_seconds": 0,
                    "candidate_floor_violation_user_intervals": 0,
                    "candidate_long_eess_violation_seconds": 0,
                    "candidate_short_eess_violation_seconds": 0,
                    "runtime_seconds": 1.0,
                }, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    script = package_root / "scripts/merge_v44_scheduling_development.py"
    completed = subprocess.run(
        [
            sys.executable, str(script),
            "--task-root", str(task_root),
            "--campaign-run-root", str(campaign_root),
            "--diagnosis-audit", str(diagnosis),
            "--output-dir", str(output),
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    summary = json.loads(
        (output / "V44_SCHEDULING_DEVELOPMENT_SUMMARY.json")
        .read_text(encoding="utf-8")
    )
    assert summary["status"].startswith("PASS_V4_4_")
    assert summary["scheduling_success_interval_count"] == 1736
    assert summary["candidate_floor_violation_user_seconds"] == 0
    assert summary["failed_seed_bounded_scope_pass_count"] == 11
    assert summary["resource_policy"]["worker_walltime"] == "00:10:00"
    assert summary["resource_policy"]["merge_walltime"] == "00:05:00"


def test_mode_coefficients_preserve_per_rf_chain_monotonic_envelope() -> None:
    args = make_same_sector_problem()
    modes, _ = generate_schedule_modes(
        gain_user_sector_stream=args["gain_user_sector_stream"],
        baseline_stream_scale=args["baseline_stream_scale"],
        active_user=args["active_user"],
        serving_bs=args["serving_bs"],
        serving_stream=args["serving_stream"],
        violating_users=args["violating_users"],
        guard_sector_limit=0,
    )
    scales = np.asarray([mode.stream_scale for mode in modes])
    assert float(scales.min()) >= 0.0
    assert float(scales.max()) <= 1.0
    # For any nonnegative per-RF-chain column powers p_{r,k}, x_k <= 1
    # implies sum_k x_k p_{r,k} <= sum_k p_{r,k}.
    rng = np.random.default_rng(20260802)
    per_chain_column_power = rng.random((64, scales.shape[1], scales.shape[2]))
    used = np.einsum("mbk,rbk->mrb", scales, per_chain_column_power)
    envelope = np.sum(per_chain_column_power, axis=2)
    assert np.all(used <= envelope[None, :, :] + 1e-14)


def test_guard_ranking_includes_dominant_eess_sector() -> None:
    gain = np.zeros((1, 7, 1), dtype=np.float64)
    gain[0, 0, 0] = 2.0
    gain[0, 1:6, 0] = np.array([10.0, 8.0, 6.0, 4.0, 2.0])
    baseline = np.ones((7, 1), dtype=np.float64)
    leakage = np.full((7, 1), 1e-6, dtype=np.float64)
    leakage[6, 0] = 1.0
    modes, _ = generate_schedule_modes(
        gain_user_sector_stream=gain,
        baseline_stream_scale=baseline,
        active_user=np.asarray([True]),
        serving_bs=np.asarray([0]),
        serving_stream=np.asarray([0]),
        violating_users=(0,),
        guard_sector_limit=2,
        leakage_sector_stream=leakage,
        long_kappa_second_sector=np.ones((2, 7), dtype=np.float64),
        short_kappa_second_sector=np.ones((2, 7), dtype=np.float64),
        long_allowance_second=np.ones(2, dtype=np.float64),
        short_allowance_second=np.ones(2, dtype=np.float64),
        coupling_uplift_db=0.0,
    )
    nonbaseline = [mode for mode in modes if mode.changed_sectors]
    assert nonbaseline
    guard_sets = {mode.guard_sectors for mode in nonbaseline}
    assert guard_sets == {(1, 6)}


def test_emergency_return_is_retrievable_and_classified_partial(
    package_root: Path,
    tmp_path: Path,
) -> None:
    import hashlib
    import zipfile

    name = "FR3_RORQUAL_V4_4_PROTECTED_SUBBAND_SCHEDULING_DEVELOPMENT_999_EMERGENCY"
    stage = tmp_path / name
    stage.mkdir()
    (stage / "EMERGENCY_RETURN_STATUS.json").write_text(
        json.dumps({
            "schema_version": 1,
            "status": "EMERGENCY_RETURN_PRIMARY_PACKAGING_FAILED",
            "primary_packaging_exit_code": 90,
            "channel_regenerated": False,
            "gpu_requested": False,
            "campaign_rerun_authorized": False,
        }, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest_lines = []
    for path in sorted(stage.rglob("*")):
        if path.is_file():
            manifest_lines.append(
                f"{hashlib.sha256(path.read_bytes()).hexdigest()}  "
                f"{path.relative_to(stage).as_posix()}"
            )
    (stage / "RETURN_MANIFEST.sha256").write_text(
        "\n".join(manifest_lines) + "\n",
        encoding="utf-8",
    )
    archive = tmp_path / f"{name}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=f"{name}/{path.relative_to(stage).as_posix()}")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    output = tmp_path / "emergency_verification.json"
    _run_script(
        package_root / "scripts/verify_v44_scheduling_return.py",
        "--return-zip", str(archive),
        "--expected-sha256", digest,
        "--output-json", str(output),
    )
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["emergency_return"] is True
    assert record["return_completeness"] == "PARTIAL"
    assert record["scientific_pass"] is False
    assert record["metadata_status"] == "EMERGENCY_RETURN_PRIMARY_PACKAGING_FAILED"


def test_real_diagnosis_mode_count_upper_bound_is_within_cap(package_root: Path) -> None:
    import pandas as pd
    archive = package_root / "immutable_bindings/FR3_RORQUAL_V4_3_FAILED_SEED_DIAGNOSIS_18150465.zip"
    with tempfile.TemporaryDirectory() as temp:
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(temp)
            archive_root = Path(temp) / zf.namelist()[0].split("/", 1)[0]
        frame = pd.read_csv(archive_root / "merged/AFFECTED_USER_DIAGNOSIS_ALL_SEEDS.csv")
    keys = ["campaign_seed", "pass_slot", "interval_index"]
    maximum = 0
    for _, interval in frame.groupby(keys):
        option_count = 1
        for _, sector in interval.groupby("serving_sector"):
            target_streams = int(sector["serving_stream"].nunique())
            # baseline + one singleton per target + full-active + mute.
            option_count *= target_streams + 3
        maximum = max(maximum, option_count)
    assert maximum == 256
    assert maximum <= 512
