from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def test_contract_is_one_seed_only_and_no_tuning():
    c = json.loads((ROOT / "config/HOLDOUT_COMPLETION_REPAIR_CONTRACT.json").read_text())
    assert c["scope"]["rerun_seed_list"] == [44052]
    assert c["scope"]["new_seeds_authorized"] is False
    assert c["scope"]["automatic_algorithm_tuning_authorized"] is False
    repair = c["seed44052_completion"]
    assert repair["observed_required_mode_count"] == 7776
    assert repair["original_mode_count_guard"] == 4096
    assert repair["repaired_mode_count_guard"] == 8192
    assert repair["action_library_definition_changed"] is False


def test_real_incomplete_holdout_audit_passes(tmp_path):
    result = tmp_path / "audit.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/audit_incomplete_holdout.py"),
            "--holdout-return-zip",
            str(ROOT / "immutable_bindings/FR3_RORQUAL_V4_5_FRESH_HOLDOUT_18163102.zip"),
            "--output-json",
            str(result),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    value = json.loads(result.read_text())
    assert value["status"] == "PASS_HOLDOUT_COMPLETION_REPAIR_REQUIRED_AND_WELL_SCOPED"
    assert value["source_supported_facts"]["complete_seed_result_count"] == 29
    assert value["source_supported_facts"]["payload_validator_false_alarm_seed_count"] == 10
    assert value["source_supported_facts"]["missing_seed_result"] == 44052
    assert value["scientific_inference"]["repair_changes_action_space"] is False


def test_repaired_payload_equation_is_declared():
    text = (ROOT / "scripts/validate_seed_result_repaired.py").read_text()
    assert "4 * schedule_nonzero_counts" in text
    assert "2 * schedule_mutable_counts" in text
    assert "PAYLOAD_LOWER_BOUND_CONTRACT_REPAIR=PASS" in text


def test_declared_7776_mode_library_fits_repaired_guard(tmp_path):
    inner = ROOT / "immutable_bindings/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_5_HOLDOUT_v1.zip"
    with zipfile.ZipFile(inner) as zf:
        zf.extractall(tmp_path)
    sys.path.insert(0, str(tmp_path / "src"))
    try:
        from fr3_cbf import companion_aware_scheduler as scheduler
        assert scheduler.MAX_MODE_COUNT == 4096
        scheduler.MAX_MODE_COUNT = 8192
        users, sectors, streams = 228, 57, 4
        gain = np.ones((users, sectors, streams), dtype=float)
        baseline = np.ones((sectors, streams), dtype=float)
        serving = np.repeat(np.arange(sectors), streams)[:users]
        stream = np.tile(np.arange(streams), sectors)[:users]
        active = np.ones(users, dtype=bool)
        modes, critical = scheduler.generate_schedule_modes(
            gain_user_sector_stream=gain,
            baseline_stream_scale=baseline,
            active_user=active,
            serving_bs=serving,
            serving_stream=stream,
            violating_users=[0, 4, 8, 12, 16],
            guard_sector_limit=4,
        )
        assert critical == (0, 1, 2, 3, 4)
        assert len(modes) == 7776
        assert len(modes) <= scheduler.MAX_MODE_COUNT
    finally:
        sys.path.pop(0)
        for key in list(sys.modules):
            if key == "fr3_cbf" or key.startswith("fr3_cbf."):
                sys.modules.pop(key, None)


def test_launcher_records_non_scientific_overlay():
    text = (ROOT / "scripts/run_seed44052_capacity_completion.py").read_text()
    assert "IMPLEMENTATION_CAPACITY_REPAIR_NOT_ALGORITHM_TUNING" in text
    assert "scientific_source_files_modified\": False" in text
    assert "action_library_definition_changed\": False" in text
    assert "--reuse-channel" in text


def test_wrappers_keep_original_terminal_policy():
    text = (ROOT / "wrappers/RUN_V45_HOLDOUT_COMPLETION_FROM_WSL.sh").read_text()
    assert "WSL_TERMINAL_CLOSE_REQUESTED=NO" in text
    assert "RERUN_SEEDS=44052_ONLY" in text
    assert "AUTOMATIC_EXTRA_SEEDS_AUTHORIZED=NO" in text


def test_sidecars_are_basename_only():
    for path in (ROOT / "immutable_bindings").glob("*.zip.sha256"):
        parts = path.read_text().split()
        assert len(parts) == 2
        assert Path(parts[1]).name == parts[1]
        assert "/" not in parts[1] and "\\" not in parts[1]


def test_completed_holdout_audit_and_tex_generation(tmp_path):
    import pandas as pd

    merged = tmp_path / "merged"
    merged.mkdir()
    audit = {
        "seed_count": 30,
        "cell_count": 1350,
        "safety_gates_pass": True,
        "valid_holdout_result": True,
        "primary_superiority_met": True,
        "primary_bootstrap": {
            "point_estimate": 0.25,
            "lower_95": 0.19,
            "upper_95": 0.31,
        },
        "claim_boundary": "FRESH_HOLDOUT_TEST",
        "floor_zero": False,
        "seed_hard_gate_pass_count": 18,
        "floor_metrics": {
            "floor_violation_user_seconds": 100,
            "floor_violation_user_intervals": 20,
            "maximum_normalized_floor_shortfall": 0.2,
        },
        "floor_reduction": {
            "versus_predictive_percent": 80.0,
            "versus_static_percent": 82.0,
        },
    }
    (merged / "PHASE1_MERGED_AUDIT.json").write_text(json.dumps(audit))
    pd.DataFrame(
        {
            "campaign_seed": list(range(44030, 44060)),
            "candidate_minus_static_final_pf": [0.25] * 30,
        }
    ).to_csv(merged / "PHASE1_SEED_CLUSTER_EFFECTS.csv", index=False)
    pd.DataFrame(
        {
            "method_id": [
                "candidate_v4_5_companion_aware_protected_subband_scheduling"
            ] * 30,
            "long_violation_seconds": [0] * 30,
            "short_violation_seconds": [0] * 30,
            "candidate_unresolved_deployable_intervals": [1] * 30,
            "candidate_network_wide_shutdown_intervals": [0] * 30,
            "candidate_q0_envelope_deployable_actions": [0] * 30,
        }
    ).to_csv(merged / "PHASE1_ALL_CELL_SUMMARY.csv", index=False)
    seed_root = tmp_path / "seed_result"
    seed_root.mkdir()
    (seed_root / "IMPLEMENTATION_CAPACITY_OVERLAY.json").write_text(
        json.dumps(
            {
                "classification": "IMPLEMENTATION_CAPACITY_REPAIR_NOT_ALGORITHM_TUNING",
                "action_library_definition_changed": False,
            }
        )
    )
    output_json = tmp_path / "audit.json"
    output_tex = tmp_path / "table.tex"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/audit_completed_holdout.py"),
            "--merged-root",
            str(merged),
            "--seed44052-result-root",
            str(seed_root),
            "--output-json",
            str(output_json),
            "--output-tex",
            str(output_tex),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    value = json.loads(output_json.read_text())
    assert value["paper_writing_authorized"] is True
    assert value["implementation_repair_sensitivity"]["action_library_definition_changed"] is False
    assert "Fresh-holdout summary" in output_tex.read_text()


def test_completion_return_packaging_is_portable(tmp_path):
    run = tmp_path / "run"
    merged = tmp_path / "merged"
    result = run / "results" / "seed_44052" / "result"
    channel = run / "results" / "seed_44052" / "channel"
    result.mkdir(parents=True)
    channel.mkdir(parents=True)
    merged.mkdir()
    (result / "SEED_RESULT.json").write_text("{}\n")
    (result / "RESULT_FILE_MANIFEST.json").write_text("{}\n")
    (result / "IMPLEMENTATION_CAPACITY_OVERLAY.json").write_text("{}\n")
    (channel / "CHANNEL_RECORD.json").write_text("{}\n")
    (merged / "PHASE1_MERGED_AUDIT.json").write_text("{}\n")
    audit = tmp_path / "completion.json"
    tex = tmp_path / "table.tex"
    audit.write_text("{}\n")
    tex.write_text("% test\n")
    output_dir = tmp_path / "return"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/package_completion_return.py"),
            "--run-root",
            str(run),
            "--repair-package-root",
            str(ROOT),
            "--merged-root",
            str(merged),
            "--completion-audit",
            str(audit),
            "--completion-tex",
            str(tex),
            "--seed-job-id",
            "123",
            "--merge-job-id",
            "124",
            "--output-dir",
            str(output_dir),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    archive = output_dir / "FR3_RORQUAL_V4_5_HOLDOUT_COMPLETION_R1_123.zip"
    sidecar = Path(str(archive) + ".sha256")
    assert archive.is_file() and sidecar.is_file()
    parts = sidecar.read_text().split()
    assert parts[1] == archive.name
    with zipfile.ZipFile(archive) as zf:
        assert zf.testzip() is None
        roots = {name.split("/", 1)[0] for name in zf.namelist() if "/" in name}
        assert roots == {archive.stem}
        manifest = zf.read(f"{archive.stem}/RETURN_MANIFEST.sha256").decode().splitlines()
        assert manifest


def test_resource_and_failure_return_policy_is_bounded():
    remote = (ROOT / "wrappers/REMOTE_ORCHESTRATE_V45_HOLDOUT_COMPLETION.sh").read_text()
    local = (ROOT / "wrappers/RUN_V45_HOLDOUT_COMPLETION_FROM_WSL.sh").read_text()
    assert "#SBATCH --time=00:12:00" in remote
    assert "#SBATCH --mem=16G" in remote
    assert "#SBATCH --time=00:05:00" in remote
    assert "#SBATCH --mem=8G" in remote
    assert "#SBATCH --gres" not in remote
    assert "REMOTE_FAILURE_RETURN_PACKAGING=PASS" in remote
    assert "LOCAL_FAILURE_RETURN_PACKAGING=PASS" in local
    assert "rsync" not in local
