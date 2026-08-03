from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/HOLDOUT_COMPLETION_R2_CONTRACT.json"
HOLDOUT = ROOT / "immutable_bindings/FR3_RORQUAL_V4_5_FRESH_HOLDOUT_18163102.zip"
R1 = ROOT / "immutable_bindings/FR3_RORQUAL_V4_5_HOLDOUT_COMPLETION_R1_18207112.zip"
JOB_ZIP = ROOT / "immutable_bindings/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_5_HOLDOUT_v1.zip"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *map(str, args)],
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    )


def extract_job(tmp_path: Path) -> Path:
    job = tmp_path / "job"
    job.mkdir()
    with zipfile.ZipFile(JOB_ZIP) as zf:
        assert zf.testzip() is None
        zf.extractall(job)
    return job


def test_immutable_bindings_and_r1_timeout_audit(tmp_path: Path) -> None:
    contract = json.loads(CONTRACT.read_text())
    assert sha256_file(HOLDOUT) == contract["existing_holdout_return_sha256"]
    assert sha256_file(R1) == contract["prior_completion_r1_return_sha256"]
    out = tmp_path / "audit.json"
    result = run(
        ROOT / "scripts/audit_r1_timeout.py",
        "--contract", CONTRACT,
        "--r1-return", R1,
        "--holdout-return", HOLDOUT,
        "--output-json", out,
    )
    assert "R1_TIMEOUT_AUDIT=PASS" in result.stdout
    audit = json.loads(out.read_text())
    assert audit["source_supported_facts"]["r1_seed_job_state"] == "TIMEOUT"
    assert audit["source_supported_facts"]["r1_batch_maxrss_kib"] == 764704
    assert audit["scientific_inference"]["memory_is_not_limiting"] is True
    assert audit["scientific_inference"]["selected_pass_walltime"] == "00:20:00"


def test_pass_parallel_equivalence_audit(tmp_path: Path) -> None:
    job = extract_job(tmp_path)
    out = tmp_path / "equivalence.json"
    result = run(
        ROOT / "scripts/audit_pass_parallel_equivalence.py",
        "--job-package-root", job,
        "--output-json", out,
    )
    assert "PASS_PARALLELIZATION_SCIENTIFIC_EQUIVALENCE=PASS" in result.stdout
    value = json.loads(out.read_text())
    assert value["source_supported_facts"]["cross_pass_output_state_propagated"] is False
    assert value["scientific_inference"]["five_pass_assembly_is_equivalent_to_original_serial_loop"] is True


def test_native_authorization_scope(tmp_path: Path) -> None:
    job = extract_job(tmp_path)
    token = tmp_path / "token.json"
    result = run(
        ROOT / "scripts/issue_seed44052_r2_authorization.py",
        "--job-package-root", job,
        "--completion-contract", CONTRACT,
        "--output", token,
    )
    assert "NATIVE_AUTHORIZATION_GUARD=PASS" in result.stdout
    value = json.loads(token.read_text())
    assert value["execution_wrapper_restriction"] == "RUN_ONLY_SEED_44052_PASSES_0_TO_4_REUSE_EXISTING_CHANNEL"
    assert value["automatic_extra_seed_or_algorithm_tuning_authorized"] is False
    assert 44052 in value["allowed_seeds"]


def _extract_nested_reference(tmp_path: Path) -> tuple[Path, dict, pd.DataFrame, bytes]:
    with zipfile.ZipFile(HOLDOUT) as outer:
        nested_name = next(
            name for name in outer.namelist()
            if name.endswith("seed_returns/FR3_PHASE1_SEED_44051_RETURN.zip")
        )
        nested_bytes = outer.read(nested_name)
        channel_name = next(
            name for name in outer.namelist()
            if name.endswith("seed_summaries/seed_44052/CHANNEL_RECORD.json")
        )
        channel_bytes = outer.read(channel_name)
    nested_root = tmp_path / "nested"
    nested_root.mkdir()
    with zipfile.ZipFile(io.BytesIO(nested_bytes)) as zf:
        assert zf.testzip() is None
        zf.extractall(nested_root)
    result_root = next(nested_root.rglob("result"))
    seed_result = json.loads((result_root / "SEED_RESULT.json").read_text())
    cells = pd.read_csv(result_root / "CELL_SUMMARY.csv")
    return result_root, seed_result, cells, channel_bytes


def test_five_pass_assembly_and_repaired_validator(tmp_path: Path) -> None:
    job = extract_job(tmp_path)
    token = tmp_path / "token.json"
    run(
        ROOT / "scripts/issue_seed44052_r2_authorization.py",
        "--job-package-root", job,
        "--completion-contract", CONTRACT,
        "--output", token,
    )
    reference, seed_result, cells, channel_bytes = _extract_nested_reference(tmp_path)
    seed_root = tmp_path / "seed_44052"
    (seed_root / "channel").mkdir(parents=True)
    (seed_root / "channel/CHANNEL_RECORD.json").write_bytes(channel_bytes)
    pass_root = tmp_path / "passes"
    pass_root.mkdir()
    token_sha = sha256_file(token)
    channel_sha = hashlib.sha256(channel_bytes).hexdigest()

    for slot in range(5):
        out = pass_root / f"pass_{slot}"
        out.mkdir()
        frame = cells.loc[cells["pass_slot"] == slot].copy()
        frame["campaign_seed"] = 44052
        frame["array_index"] = 22
        frame.to_csv(out / "PASS_CELL_SUMMARY.csv", index=False)
        audit = seed_result["pass_audits"][slot]
        (out / "PASS_AUDIT.json").write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
        metadata = {
            "schema_version": 1,
            "status": "PASS_SEED44052_PROTECTED_PASS_COMPLETE",
            "seed": 44052,
            "array_index": 22,
            "pass_slot": slot,
            "package_id": seed_result["package_id"],
            "candidate_source_manifest_sha256": seed_result["candidate_source_manifest_sha256"],
            "authorization_token_sha256": token_sha,
            "mode_capacity_original": 4096,
            "mode_capacity_runtime": 8192,
            "required_mode_count": 7776,
            "channel_reused": True,
            "channel_regenerated": False,
            "gpu_requested": False,
            "scientific_source_files_modified": False,
            "action_library_definition_changed": False,
            "elapsed_seconds": 1.0 + slot,
            "architecture_id": seed_result["architecture"]["architecture_id"],
            "rf_chains": seed_result["architecture"]["rf_chains"],
            "analog_phase_bits": seed_result["architecture"]["analog_phase_bits"],
            "architecture_audit": seed_result["architecture"]["full_load_audit"],
            "nominal_total_sum_se_bps_hz": seed_result["architecture"]["nominal_total_sum_se_bps_hz"],
            "channel_record_sha256": channel_sha,
        }
        (out / "PASS_RESULT_METADATA.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
        for name in (f"PASS_{slot}_METHOD_TRACES.npz", f"PASS_{slot}_CANDIDATE_ACTION_TRACE.npz"):
            (out / name).write_bytes((reference / name).read_bytes())
        manifest = {}
        for path in sorted(out.iterdir()):
            if path.name != "PASS_RESULT_MANIFEST.json":
                manifest[path.name] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        (out / "PASS_RESULT_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    result = run(
        ROOT / "scripts/assemble_seed44052.py",
        "--job-package-root", job,
        "--seed-root", seed_root,
        "--pass-output-root", pass_root,
        "--completion-contract", CONTRACT,
        "--authorization-file", token,
    )
    assert "SEED44052_PASS_PARALLEL_ASSEMBLY=PASS" in result.stdout
    assembled = pd.read_csv(seed_root / "result/CELL_SUMMARY.csv")
    assert len(assembled) == 45
    assert assembled["campaign_seed"].unique().tolist() == [44052]
    assert assembled["array_index"].unique().tolist() == [22]
    assert (seed_root / "result/IMPLEMENTATION_CAPACITY_OVERLAY.json").is_file()

    validator = run(
        ROOT / "scripts/validate_seed_result_repaired.py",
        "--result-dir", seed_root / "result",
        "--package-contract", job / "JOB_PACKAGE_CONTRACT.json",
    )
    assert "FRESH_V4_5_HOLDOUT_SEED_STRUCTURAL_VALIDATION=PASS" in validator.stdout


def test_compact_return_packaging(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    completion = run_root / "holdout_completion_r2_pass_parallel"
    (completion / "slurm").mkdir(parents=True)
    (completion / "pass_outputs/pass_0").mkdir(parents=True)
    (completion / "HOLDOUT_COMPLETION_AUDIT.json").write_text("{}\n")
    (completion / "holdout_key_results.tex").write_text("% test\n")
    (completion / "R1_TIMEOUT_AUDIT.json").write_text("{}\n")
    (completion / "slurm/sacct_completion_r2.txt").write_text("test\n")
    (completion / "pass_outputs/pass_0/PASS_RESULT_METADATA.json").write_text("{}\n")
    output = tmp_path / "return"
    result = run(
        ROOT / "scripts/package_completion_r2_return.py",
        "--run-root", run_root,
        "--package-root", ROOT,
        "--completion-root", completion,
        "--pass-array-job-id", "123",
        "--assembly-job-id", "124",
        "--output-dir", output,
    )
    assert "HOLDOUT_COMPLETION_R2_RETURN_PACKAGING=PASS" in result.stdout
    archive = output / "FR3_RORQUAL_V4_5_HOLDOUT_COMPLETION_R2_123.zip"
    sidecar = Path(str(archive) + ".sha256")
    assert sidecar.read_text().split()[1] == archive.name
    with zipfile.ZipFile(archive) as zf:
        assert zf.testzip() is None
        manifest_name = next(n for n in zf.namelist() if n.endswith("RETURN_MANIFEST.sha256"))
        assert zf.read(manifest_name)


def test_resource_and_terminal_contracts() -> None:
    contract = json.loads(CONTRACT.read_text())
    strategy = contract["execution_strategy"]
    assert strategy["pass_array"] == "0-4%5"
    assert strategy["pass_worker_walltime"] == "00:20:00"
    assert strategy["pass_worker_memory"] == "4G"
    assert strategy["assembly_walltime"] == "00:05:00"
    assert strategy["gpu_requested"] is False
    assert contract["scientific_invariants"]["candidate_source_files_modified"] is False

    remote = (ROOT / "wrappers/REMOTE_ORCHESTRATE_V45_HOLDOUT_COMPLETION_R2.sh").read_text()
    local = (ROOT / "wrappers/RUN_V45_HOLDOUT_COMPLETION_R2_FROM_WSL.sh").read_text()
    assert "#SBATCH --array=0-4%5" in remote
    assert "#SBATCH --time=00:20:00" in remote
    assert "#SBATCH --mem=4G" in remote
    assert "--dependency=afterany" in remote
    assert "WSL_TERMINAL_CLOSE_REQUESTED=NO" in local
    assert "exit \"$REMOTE_WRAPPER_EXIT_CODE\"" in local


def test_no_new_seed_or_scientific_change() -> None:
    version = json.loads((ROOT / "PACKAGE_VERSION.json").read_text())
    contract = json.loads(CONTRACT.read_text())
    assert version["seed_scope"] == [44052]
    assert version["scientific_change"] is False
    assert version["gpu_requested"] is False
    assert version["new_seeds_authorized"] is False
    invariants = contract["scientific_invariants"]
    assert not any(invariants.values())


def test_channel_binding_values() -> None:
    contract = json.loads(CONTRACT.read_text())
    binding = contract["seed44052_channel_binding"]
    with zipfile.ZipFile(HOLDOUT) as zf:
        name = next(n for n in zf.namelist() if n.endswith("seed_summaries/seed_44052/CHANNEL_RECORD.json"))
        data = zf.read(name)
    record = json.loads(data)
    assert hashlib.sha256(data).hexdigest() == binding["channel_record_file_sha256"]
    assert record["frequency_response_sha256_array_bytes"] == binding["frequency_response_array_sha256"]
