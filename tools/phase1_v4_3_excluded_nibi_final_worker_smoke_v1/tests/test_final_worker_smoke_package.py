from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
LOCKED = ROOT / "immutable_bindings/locked_campaign"
REFERENCE = ROOT / "immutable_bindings/reference_seed43999"
JOB_ZIP = LOCKED / "FR3_PHASE1_NIBI_JOB_PACKAGE_V4_3_v1.zip"
METHOD_IDS = [
    "candidate_v4_3_floor_feasibility_repair",
    "robust_predictive_constrained_pf_with_sector_selective_fallback",
    "static_robust_constrained_pf_with_sector_selective_fallback",
    "delayed_myopic_constrained_pf_with_reactive_sector_fallback",
    "delayed_myopic_constrained_pf_unshielded",
    "virtual_queue_unshielded",
    "uniform_protected_tone_backoff",
    "hard_spatial_null_or_exact_mute",
    "common_scale_instantaneous_noncausal_reference",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def run(*args: str, check: bool = True, env: dict[str, str] | None = None):
    return subprocess.run(
        [sys.executable, *args],
        text=True,
        capture_output=True,
        check=check,
        env=env,
    )


def extract_job(target: Path) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(JOB_ZIP) as bundle:
        bundle.extractall(target)
    return target


def make_small_channel(seed_root: Path, reference_root: Path) -> None:
    channel = seed_root / "channel"
    channel.mkdir(parents=True, exist_ok=True)
    data = np.arange(24, dtype=np.complex128).reshape(2, 3, 4)
    np.save(channel / "frequency_response.npy", data, allow_pickle=False)
    (channel / "USER_TOPOLOGY.csv").write_text("user_id\nU0\n", encoding="utf-8")
    (channel / "SECTOR_TOPOLOGY.csv").write_text("sector_id\nS0\n", encoding="utf-8")
    record = {
        "campaign_seed": 43999,
        "user_seed": 87998,
        "channel_seed": 87999,
        "frequency_response_sha256_array_bytes": hashlib.sha256(
            np.ascontiguousarray(data).tobytes()
        ).hexdigest(),
        "channel_generation": {
            "response_shape": [228, 57, 128, 9],
            "coefficients_sha256": "a" * 64,
            "delays_sha256": "b" * 64,
        },
        "files": {
            "frequency_response.npy": {
                "sha256": sha256_file(channel / "frequency_response.npy")
            },
            "USER_TOPOLOGY.csv": {
                "sha256": sha256_file(channel / "USER_TOPOLOGY.csv")
            },
            "SECTOR_TOPOLOGY.csv": {
                "sha256": sha256_file(channel / "SECTOR_TOPOLOGY.csv")
            },
        },
    }
    (channel / "CHANNEL_RECORD.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    reference_root.mkdir(parents=True, exist_ok=True)
    (reference_root / "REFERENCE_CHANNEL_RECORD.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def make_synthetic_exact_result(seed_root: Path, reference_root: Path) -> None:
    result = seed_root / "result"
    result.mkdir(parents=True, exist_ok=True)
    make_small_channel(seed_root, reference_root)

    for name in (
        "REFERENCE_ALL_METHOD_CELL_SUMMARY.csv",
        "REFERENCE_CANDIDATE_CELL_SUMMARY.csv",
        "REFERENCE_CANDIDATE_UTILITY_SUMMARY.csv",
    ):
        shutil.copy2(REFERENCE / name, reference_root / name)
    for slot in range(5):
        shutil.copy2(
            REFERENCE / f"REFERENCE_CANDIDATE_PASS_{slot}_TRACE.npz",
            reference_root / f"REFERENCE_CANDIDATE_PASS_{slot}_TRACE.npz",
        )

    comparator = pd.read_csv(reference_root / "REFERENCE_ALL_METHOD_CELL_SUMMARY.csv")
    candidate_summary = pd.read_csv(
        reference_root / "REFERENCE_CANDIDATE_CELL_SUMMARY.csv"
    )
    utility = pd.read_csv(reference_root / "REFERENCE_CANDIDATE_UTILITY_SUMMARY.csv")

    candidate_rows: list[dict[str, object]] = []
    for _, summary in candidate_summary.iterrows():
        slot = int(summary["pass_slot"])
        util = utility.loc[utility["pass_slot"] == slot].iloc[0]
        candidate_rows.append(
            {
                "method_id": METHOD_IDS[0],
                "pass_slot": slot,
                "protected_sample_count": int(summary["protected_sample_count"]),
                "interval_count": int(summary["interval_count"]),
                "long_violation_seconds": 0,
                "short_violation_seconds": 0,
                "long_maximum_excess_db": -1.0,
                "short_maximum_excess_db": -1.0,
                "eligible_floor_violation_user_intervals": 0,
                "eligible_floor_violation_user_seconds": 0,
                "total_normalized_floor_shortfall": 0.0,
                "final_moving_pf_utility": float(
                    util["candidate_final_moving_pf_utility"]
                ),
                "duration_weighted_mean_moving_pf_utility": float(
                    util["candidate_duration_weighted_mean_moving_pf_utility"]
                ),
                "protected_active_eligible_p05_bps_hz": float(
                    util["candidate_protected_active_eligible_p05_bps_hz"]
                ),
                "protected_active_eligible_geometric_mean_bps_hz": float(
                    util[
                        "candidate_protected_active_eligible_positive_geometric_mean_bps_hz"
                    ]
                ),
                "total_active_eligible_p05_bps_hz": float(
                    util["candidate_total_active_eligible_p05_bps_hz"]
                ),
                "total_active_eligible_geometric_mean_bps_hz": float(
                    util["candidate_total_active_eligible_geometric_mean_bps_hz"]
                ),
                "sector_mute_interval_count": 0,
                "intervals_with_any_sector_mute": 0,
                "maximum_muted_sector_count": 0,
                "candidate_strict_local_scope_gate": "PASS",
                "candidate_strict_post_mode_power_gate": "PASS",
                "candidate_q0_envelope_deployable_actions": 0,
                "candidate_unresolved_deployable_intervals": 0,
                "candidate_network_wide_shutdown_intervals": 0,
                "candidate_maximum_strict_post_mode_power_ratio": 0.999999,
                "candidate_information_exchange_locality_certified": False,
                "candidate_local_grid_repair_intervals": int(
                    summary["local_frozen_grid_repair_intervals"]
                ),
                "candidate_local_stream_repair_intervals": int(
                    summary["local_stream_repair_intervals"]
                ),
            }
        )

    cell_rows: list[dict[str, object]] = []
    for slot in range(5):
        cell_rows.append(next(row for row in candidate_rows if row["pass_slot"] == slot))
        for method in METHOD_IDS[1:]:
            row = comparator.loc[
                (comparator["pass_slot"] == slot) & (comparator["method_id"] == method)
            ].iloc[0]
            cell_rows.append(row.to_dict())
    cells = pd.DataFrame(cell_rows)
    cells.to_csv(result / "CELL_SUMMARY.csv", index=False)

    paired = utility[
        [
            "pass_slot",
            "candidate_minus_predictive_final_pf",
            "candidate_minus_predictive_duration_mean_pf",
            "candidate_minus_static_final_pf",
            "candidate_minus_static_duration_mean_pf",
        ]
    ].copy()
    paired.to_csv(result / "PRIMARY_PAIRED_EFFECTS.csv", index=False)

    for slot in range(5):
        with np.load(
            reference_root / f"REFERENCE_CANDIDATE_PASS_{slot}_TRACE.npz",
            allow_pickle=False,
        ) as ref:
            action_class = ref["action_class"]
            interval_lengths = ref["interval_lengths"]
            np.savez_compressed(
                result / f"PASS_{slot}_CANDIDATE_ACTION_TRACE.npz",
                candidate_stream_scale=ref["candidate_stream_scale"],
                candidate_action_class=action_class,
                candidate_pre_repair_sector_scale=ref[
                    "integrated_pre_repair_sector_scale"
                ],
                candidate_maximum_shortfall_trace=ref[
                    "candidate_normalized_shortfall"
                ],
                candidate_changed_stream_coefficient_count_trace=np.zeros(
                    len(interval_lengths), dtype=np.int64
                ),
                candidate_changed_sector_count_trace=np.zeros(
                    len(interval_lengths), dtype=np.int64
                ),
                candidate_incremental_float32_payload_lower_bound_bytes_trace=np.zeros(
                    len(interval_lengths), dtype=np.int64
                ),
                interval_lengths=interval_lengths,
            )
            arrays: dict[str, np.ndarray] = {
                "method_ids": np.asarray(METHOD_IDS),
                "interval_lengths": interval_lengths,
                "m0_long_ratio": ref["candidate_long_ratio"],
                "m0_short_ratio": ref["candidate_short_ratio"],
                "m0_floor_count": ref["candidate_floor_count"],
                "m0_shortfall": ref["candidate_normalized_shortfall"],
            }
            np.savez_compressed(result / f"PASS_{slot}_METHOD_TRACES.npz", **arrays)

    seed_audit = {
        "campaign_seed": 43999,
        "array_index": -1,
        "execution_stage": "EXCLUDED_FINAL_WORKER_SMOKE_SEED43999",
        "package_id": "77bec1efa2ea151a64481d6993399b82585eac3c1343d51adb0fc37da294e015",
        "candidate_source_manifest_sha256": "a2e67130c91577b83be6e14f400d0934aa6d94ac0f974956594df35eec0cb93c",
        "method_ids": METHOD_IDS,
        "cell_count": 45,
        "pass_audits": [{"pass_slot": slot} for slot in range(5)],
        "candidate_hard_gates_pass": True,
        "scientific_exit_code": 0,
    }
    (result / "SEED_RESULT.json").write_text(
        json.dumps(seed_audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest: dict[str, dict[str, int | str]] = {}
    for path in sorted(result.iterdir()):
        if path.is_file() and path.name != "RESULT_FILE_MANIFEST.json":
            manifest[path.name] = {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
    (result / "RESULT_FILE_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def make_auth_and_env(root: Path) -> tuple[Path, Path]:
    auth = root / "AUTH_RECORD.json"
    auth.write_text(
        json.dumps(
            {
                "execution_stage": "EXCLUDED_FINAL_WORKER_SMOKE_SEED43999",
                "allowed_seeds": [43999],
                "native_authorization_guard": "PASS",
                "token_in_return_bundle": False,
                "full_campaign_execution_authorized": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    env = root / "ENVIRONMENT.json"
    env.write_text(
        json.dumps(
            {
                "status": "PASS_NIBI_H100_FINAL_WORKER_ENVIRONMENT",
                "exact_reference_environment_gate": "PASS",
                "actual_versions": {
                    "torch": "2.9.1",
                    "sionna-no-rt": "2.0.1",
                    "numpy": "2.4.2",
                    "scipy": "1.17.0",
                    "pandas": "2.3.3",
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return auth, env


def test_locked_campaign_inputs_audit(tmp_path: Path) -> None:
    output = tmp_path / "audit.json"
    completed = run(
        str(SCRIPTS / "audit_locked_campaign_inputs.py"),
        "--package-root",
        str(ROOT),
        "--output",
        str(output),
    )
    value = json.loads(output.read_text(encoding="utf-8"))
    assert completed.returncode == 0
    assert value["status"] == "PASS_LOCKED_V4_3_CAMPAIGN_INPUT_AND_REVIEW_AUDIT"
    assert value["campaign_execution_authorized"] is False
    assert value["excluded_seed"] == 43999
    assert value["confirmatory_seed_count"] == 30


def test_smoke_authorization_is_native_guarded_and_seed_scoped(tmp_path: Path) -> None:
    job = extract_job(tmp_path / "job")
    token = tmp_path / "token.json"
    record = tmp_path / "record.json"
    completed = run(
        str(SCRIPTS / "issue_final_worker_smoke_authorization.py"),
        "--job-root",
        str(job),
        "--output",
        str(token),
        "--record-output",
        str(record),
        "--ttl-hours",
        "1",
        "--smoke-source-commit",
        "c" * 40,
        "--smoke-package-sha256",
        "d" * 64,
    )
    assert completed.returncode == 0
    value = json.loads(token.read_text(encoding="utf-8"))
    evidence = json.loads(record.read_text(encoding="utf-8"))
    assert value["execution_stage"] == "EXCLUDED_FINAL_WORKER_SMOKE_SEED43999"
    assert value["allowed_seeds"] == [43999]
    assert value["slurm_array_authorized"] is False
    assert value["merge_authorized"] is False
    assert evidence["native_authorization_guard"] == "PASS"
    assert evidence["full_campaign_execution_authorized"] is False

    spec = importlib.util.spec_from_file_location("guard", job / "authorization_guard.py")
    assert spec and spec.loader
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    contract = json.loads((job / "JOB_PACKAGE_CONTRACT.json").read_text())
    tampered = dict(value)
    tampered["allowed_seeds"] = [44000]
    token.write_text(json.dumps(tampered), encoding="utf-8")
    previous = os.environ.get("PHASE1_AUTHORIZATION_FILE")
    os.environ["PHASE1_AUTHORIZATION_FILE"] = str(token)
    try:
        with pytest.raises(RuntimeError, match="authorization seed list mismatch"):
            guard.require_authorization(contract)
    finally:
        if previous is None:
            os.environ.pop("PHASE1_AUTHORIZATION_FILE", None)
        else:
            os.environ["PHASE1_AUTHORIZATION_FILE"] = previous


def test_exact_synthetic_final_worker_audit_and_tamper_detection(tmp_path: Path) -> None:
    job = extract_job(tmp_path / "job")
    seed_root = tmp_path / "seed_43999"
    reference = tmp_path / "reference"
    make_synthetic_exact_result(seed_root, reference)
    auth, env = make_auth_and_env(tmp_path)
    output = tmp_path / "audit.json"
    completed = run(
        str(SCRIPTS / "audit_final_worker_smoke_result.py"),
        "--seed-root",
        str(seed_root),
        "--job-root",
        str(job),
        "--reference-root",
        str(reference),
        "--authorization-record",
        str(auth),
        "--environment",
        str(env),
        "--output",
        str(output),
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
    value = json.loads(output.read_text(encoding="utf-8"))
    assert value["status"] == "PASS_EXCLUDED_NIBI_FINAL_CAMPAIGN_WORKER_SMOKE_SEED43999"
    assert value["channel_exact_reference_gate"] == "PASS"
    assert value["candidate_reference_trace_gate"] == "PASS"
    assert value["candidate_hard_gates"] == "PASS"
    assert value["full_campaign_execution_authorized"] is False

    trace_path = seed_root / "result/PASS_0_CANDIDATE_ACTION_TRACE.npz"
    with np.load(trace_path, allow_pickle=False) as loaded:
        values = {key: loaded[key] for key in loaded.files}
    values["candidate_stream_scale"] = values["candidate_stream_scale"].copy()
    values["candidate_stream_scale"][0, 0, 0] += 1e-4
    np.savez_compressed(trace_path, **values)
    manifest_path = seed_root / "result/RESULT_FILE_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[trace_path.name] = {
        "bytes": trace_path.stat().st_size,
        "sha256": sha256_file(trace_path),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    failed = run(
        str(SCRIPTS / "audit_final_worker_smoke_result.py"),
        "--seed-root",
        str(seed_root),
        "--job-root",
        str(job),
        "--reference-root",
        str(reference),
        "--authorization-record",
        str(auth),
        "--environment",
        str(env),
        "--output",
        str(tmp_path / "tampered.json"),
        check=False,
    )
    assert failed.returncode == 42


def test_success_return_excludes_token_and_raw_channel(tmp_path: Path) -> None:
    job = extract_job(tmp_path / "job")
    run_root = tmp_path / "run"
    seed_root = run_root / "results/seed_43999"
    reference = tmp_path / "reference"
    make_synthetic_exact_result(seed_root, reference)
    auth, env = make_auth_and_env(tmp_path)
    provenance = run_root / "provenance"
    provenance.mkdir(parents=True, exist_ok=True)
    audit = provenance / "FINAL_WORKER_SMOKE_AUDIT.json"
    completed = run(
        str(SCRIPTS / "audit_final_worker_smoke_result.py"),
        "--seed-root",
        str(seed_root),
        "--job-root",
        str(job),
        "--reference-root",
        str(reference),
        "--authorization-record",
        str(auth),
        "--environment",
        str(env),
        "--output",
        str(audit),
    )
    assert completed.returncode == 0
    (provenance / "FINAL_WORKER_SMOKE_AUTHORIZATION.json").write_text(
        "forbidden token", encoding="utf-8"
    )
    (provenance / "FINAL_WORKER_SMOKE_AUTHORIZATION_RECORD.json").write_text(
        auth.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (provenance / "NIBI_H100_ENVIRONMENT.json").write_text(
        env.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (run_root / "logs").mkdir()
    (run_root / "logs/job.out").write_text("ok\n", encoding="utf-8")
    output = tmp_path / "return.zip"
    packaged = run(
        str(SCRIPTS / "package_final_worker_smoke_return.py"),
        "--run-root",
        str(run_root),
        "--smoke-package-root",
        str(ROOT),
        "--job-package-root",
        str(job),
        "--job-id",
        "12345",
        "--slurm-state",
        "COMPLETED",
        "--slurm-exit-code",
        "0:0",
        "--worker-exit-code",
        "0",
        "--structural-validator-exit-code",
        "0",
        "--pass-validator-exit-code",
        "0",
        "--independent-audit-exit-code",
        "0",
        "--output",
        str(output),
    )
    assert packaged.returncode == 0
    validated = run(
        str(SCRIPTS / "validate_final_worker_smoke_return.py"),
        "--return-zip",
        str(output),
    )
    assert validated.returncode == 0, validated.stderr + validated.stdout
    with zipfile.ZipFile(output) as bundle:
        names = bundle.namelist()
    assert not any(name.endswith("frequency_response.npy") for name in names)
    assert not any("FINAL_WORKER_SMOKE_AUTHORIZATION.json" in name for name in names)


def test_local_failure_return_is_portable(tmp_path: Path) -> None:
    local = tmp_path / "local"
    local.mkdir()
    (local / "LOCAL_WSL_ORCHESTRATOR.log").write_text("failure\n", encoding="utf-8")
    completed = run(
        str(SCRIPTS / "package_local_failure.py"),
        "--local-return",
        str(local),
        "--exit-code",
        "77",
        "--command",
        "synthetic failure",
    )
    assert completed.returncode == 0
    archive = local / "FR3_V4_3_NIBI_FINAL_WORKER_SMOKE_LOCAL_FAILURE.zip"
    sidecar = Path(str(archive) + ".sha256")
    assert archive.is_file() and sidecar.is_file()
    digest, name = sidecar.read_text(encoding="utf-8").split()
    assert digest == sha256_file(archive)
    assert name == archive.name
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None


def test_diagnostic_return_is_retrievable_and_non_authorizing(tmp_path: Path) -> None:
    job = extract_job(tmp_path / "job")
    run_root = tmp_path / "run"
    (run_root / "provenance").mkdir(parents=True)
    (run_root / "logs").mkdir()
    (run_root / "provenance/REMOTE_RUN_SUMMARY.env").write_text(
        "SLURM_STATE=FAILED\nFULL_CAMPAIGN_EXECUTION_AUTHORIZED=NO\n",
        encoding="utf-8",
    )
    (run_root / "logs/failure.err").write_text("synthetic failure\n", encoding="utf-8")
    output = tmp_path / "diagnostic.zip"
    packaged = run(
        str(SCRIPTS / "package_final_worker_smoke_return.py"),
        "--run-root",
        str(run_root),
        "--smoke-package-root",
        str(ROOT),
        "--job-package-root",
        str(job),
        "--job-id",
        "54321",
        "--slurm-state",
        "FAILED",
        "--slurm-exit-code",
        "43:0",
        "--worker-exit-code",
        "99",
        "--structural-validator-exit-code",
        "99",
        "--pass-validator-exit-code",
        "99",
        "--independent-audit-exit-code",
        "99",
        "--output",
        str(output),
    )
    assert packaged.returncode == 0
    validated = run(
        str(SCRIPTS / "validate_final_worker_smoke_return.py"),
        "--return-zip",
        str(output),
        check=False,
    )
    assert validated.returncode == 20
    assert "RETURN_STATUS=DIAGNOSTIC_EXCLUDED_NIBI_FINAL_WORKER_SMOKE_RETURN_READY" in validated.stdout
    with zipfile.ZipFile(output) as bundle:
        names = bundle.namelist()
    assert not any("AUTHORIZATION.json" in name for name in names)
    assert not any(name.endswith("frequency_response.npy") for name in names)


def test_wrappers_enforce_one_excluded_job_and_no_campaign_execution() -> None:
    nibi = (ROOT / "wrappers/NIBI_FINAL_WORKER_SMOKE_H100.sh").read_text()
    remote = (
        ROOT / "wrappers/REMOTE_ORCHESTRATE_V4_3_NIBI_FINAL_WORKER_SMOKE.sh"
    ).read_text()
    wsl = (
        ROOT / "wrappers/RUN_V4_3_NIBI_FINAL_WORKER_SMOKE_FROM_WSL.sh"
    ).read_text()
    combined = nibi + remote + wsl
    assert "--seed \"$SEED\"" in nibi
    assert "SEED=43999" in nibi
    assert "--gpus-per-node=h100:1" in remote
    assert "--array" not in remote
    assert "phase1_merge_worker" not in combined
    assert "SLURM_ARRAY_USED=NO" in combined
    assert "MERGE_JOB_SUBMITTED=NO" in combined
    assert "FULL_CAMPAIGN_EXECUTION_AUTHORIZED=NO" in combined
    assert "PRESERVED_CHANNEL_REUSED=NO" in combined
    assert "--reuse-channel" not in nibi
    assert "rm -f \"$TOKEN\"" in remote
    assert "NO_PRIOR_FINAL_WORKER_SMOKE_EVIDENCE_GATE=PASS" in wsl
    assert "AUTOMATIC_SMOKE_RERUN_AUTHORIZED=NO" in wsl
    assert "wsl.exe --terminate" not in combined
    assert "shutdown.exe" not in combined.lower()
    assert "wsl --shutdown" not in combined.lower()
    assert "poweroff" not in combined.lower()


def test_git_workflow_simulation(tmp_path: Path) -> None:
    output = tmp_path / "git.json"
    completed = run(
        str(SCRIPTS / "simulate_git_workflow.py"),
        "--output",
        str(output),
    )
    assert completed.returncode == 0
    value = json.loads(output.read_text(encoding="utf-8"))
    assert value["status"] == "PASS_GIT_NORMAL_CONCURRENT_AND_STALE_NON_FORCE_SIMULATION"
    assert value["newer_work_overwritten"] is False
    assert all(value["checks"].values())


def test_policy_and_scope_audit(tmp_path: Path) -> None:
    output = tmp_path / "policy.json"
    completed = run(
        str(SCRIPTS / "audit_policy_scope.py"),
        "--package-root",
        str(ROOT),
        "--output",
        str(output),
    )
    assert completed.returncode == 0
    value = json.loads(output.read_text(encoding="utf-8"))
    assert value["status"] == "PASS_EXCLUDED_ONE_SEED_SMOKE_POLICY_AND_SCOPE_AUDIT"
    assert value["full_campaign_execution_authorized"] is False
    assert all(value["checks"].values())
