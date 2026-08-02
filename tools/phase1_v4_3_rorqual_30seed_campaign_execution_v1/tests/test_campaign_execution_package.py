from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def test_authorization_prerequisites_exact() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/audit_authorization_prerequisites.py"), "--package-root", str(ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "FULL_CAMPAIGN_AUTHORIZATION_PREREQUISITE_AUDIT=PASS" in completed.stdout
    assert "CAMPAIGN_EXECUTION_AUTHORIZED=YES_EXACT_PACKAGE_AND_SEEDS_ONLY" in completed.stdout


def test_exact_immutable_hashes_and_review() -> None:
    contract = json.loads((ROOT / "config/FULL_CAMPAIGN_AUTHORIZATION_CONTRACT.json").read_text())
    imm = ROOT / "immutable_bindings"
    assert sha256_file(imm / "FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2.zip") == contract["immutable_bindings"]["rorqual_r2_job_package_sha256"]
    assert sha256_file(imm / "FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2_INDEPENDENT_REVIEW.zip") == contract["immutable_bindings"]["rorqual_r2_review_sha256"]
    review = json.loads((imm / "INDEPENDENT_REVIEW_VERDICT.json").read_text())
    assert review["candidate_source_changed"] is False
    assert review["status"].startswith("PASS_CORRECTED_RORQUAL_NATIVE_LOCKED_30_SEED")


def test_authorization_token_accepted_by_native_guard(tmp_path: Path) -> None:
    job_zip = ROOT / "immutable_bindings/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2.zip"
    job_root = tmp_path / "job"
    job_root.mkdir()
    with zipfile.ZipFile(job_zip) as z:
        z.extractall(job_root)
    token = tmp_path / "token.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/issue_full_campaign_authorization.py"),
            "--job-package-root", str(job_root),
            "--authorization-contract", str(ROOT / "config/FULL_CAMPAIGN_AUTHORIZATION_CONTRACT.json"),
            "--output", str(token),
            "--expiry-days", "14",
            "--authorization-package-sha256", "a" * 64,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    value = json.loads(token.read_text())
    assert value["execution_authorized"] is True
    assert value["execution_stage"] == "FULL_30_SEED_CONFIRMATORY_CAMPAIGN"
    assert value["allowed_seeds"] == list(range(44000, 44030))
    assert token.stat().st_mode & 0o777 == 0o600


def create_tiny_seed_return(seed_root: Path, seed: int) -> None:
    import zipfile
    result = seed_root / "result"
    channel = seed_root / "channel"
    result.mkdir(parents=True)
    channel.mkdir()
    audit = {
        "campaign_seed": seed,
        "candidate_hard_gates_pass": True,
        "scientific_exit_code": 0,
    }
    (result / "SEED_RESULT.json").write_text(json.dumps(audit) + "\n")
    (result / "RESULT_FILE_MANIFEST.json").write_text("{}\n")
    (result / "CELL_SUMMARY.csv").write_text("method_id,pass_slot\ncandidate_v4_3_floor_feasibility_repair,0\n")
    (result / "PRIMARY_PAIRED_EFFECTS.csv").write_text("pass_slot,candidate_minus_static_final_pf\n0,1\n")
    (channel / "CHANNEL_RECORD.json").write_text(json.dumps({"campaign_seed": seed}) + "\n")
    zpath = seed_root / f"FR3_PHASE1_SEED_{seed}_RETURN.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"FR3_PHASE1_SEED_{seed}_RETURN/SEED_RETURN_METADATA.json", "{}\n")
    Path(str(zpath) + ".sha256").write_text(f"{sha256_file(zpath)}  {zpath.name}\n")


def test_synthetic_success_return_packaging_and_audit(tmp_path: Path) -> None:
    run = tmp_path / "run"
    job = tmp_path / "job"
    out = tmp_path / "return"
    run.mkdir(); job.mkdir(); out.mkdir()
    with zipfile.ZipFile(ROOT / "immutable_bindings/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2.zip") as z:
        z.extractall(job)
    for seed in range(44000, 44030):
        create_tiny_seed_return(run / "results" / f"seed_{seed}", seed)
    merged = run / "merged"; merged.mkdir()
    audit = {
        "all_hard_gates_pass": True,
        "go_condition_met": True,
        "primary_bootstrap": {"point_estimate": 1.0, "lower_95": 0.2, "upper_95": 1.8},
    }
    (merged / "PHASE1_MERGED_AUDIT.json").write_text(json.dumps(audit) + "\n")
    with zipfile.ZipFile(merged / "FR3_PHASE1_MERGED_REVIEW_RETURN.zip", "w") as z:
        z.writestr("PHASE1_MERGED_AUDIT.json", json.dumps(audit))
    merged_zip = merged / "FR3_PHASE1_MERGED_REVIEW_RETURN.zip"
    Path(str(merged_zip) + ".sha256").write_text(f"{sha256_file(merged_zip)}  {merged_zip.name}\n")
    status = run / "status"; status.mkdir()
    for name in ("ARRAY_SUMMARY_EXIT_CODE.txt", "MERGE_WORKER_EXIT_CODE.txt", "MERGED_VALIDATOR_EXIT_CODE.txt"):
        (status / name).write_text("0\n")
    token_public = {
        "authorization_decision_id": json.loads((ROOT / "config/FULL_CAMPAIGN_AUTHORIZATION_CONTRACT.json").read_text())["authorization_decision_id"],
        "authorization_expires_utc": "2099-01-01T00:00:00+00:00",
        "execution_stage": "FULL_30_SEED_CONFIRMATORY_CAMPAIGN",
        "allowed_seeds": list(range(44000, 44030)),
    }
    token_meta = tmp_path / "token_meta.json"
    token_meta.write_text(json.dumps({"authorization_token_sha256": "b" * 64, "token_public_fields": token_public}) + "\n")
    completed = subprocess.run(
        [
            sys.executable, str(ROOT / "scripts/package_campaign_return.py"),
            "--run-root", str(run),
            "--job-package-root", str(job),
            "--authorization-contract", str(ROOT / "config/FULL_CAMPAIGN_AUTHORIZATION_CONTRACT.json"),
            "--authorization-token-metadata", str(token_meta),
            "--authorization-package-sha256", "c" * 64,
            "--array-job-id", "1000", "--merge-job-id", "1001", "--finalizer-job-id", "1002",
            "--output-dir", str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return_zip = out / "FR3_RORQUAL_V4_3_R2_30SEED_CAMPAIGN_1000.zip"
    audit_completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/audit_campaign_return.py"), "--return-zip", str(return_zip)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert audit_completed.returncode == 0, audit_completed.stdout + audit_completed.stderr
    assert "SEED_RETURN_COUNT=30" in audit_completed.stdout
    assert "GO_CONDITION_MET=True" in audit_completed.stdout


def test_authorization_is_exactly_limited() -> None:
    contract = json.loads((ROOT / "config/FULL_CAMPAIGN_AUTHORIZATION_CONTRACT.json").read_text())
    scope = contract["authorization_is_limited_to"]
    assert scope["cluster"] == "rorqual"
    assert scope["allowed_seeds"] == list(range(44000, 44030))
    assert scope["candidate_source_change_permitted"] is False
    assert scope["channel_reuse_permitted"] is False
    assert scope["total_cells"] == 1350


def test_no_authorization_token_is_packaged() -> None:
    forbidden = []
    for path in ROOT.rglob("*"):
        if path.is_file() and "AUTHORIZATION" in path.name.upper() and path.suffix == ".json":
            value = json.loads(path.read_text())
            if value.get("execution_authorized") is True and "TOKEN" in path.name.upper():
                forbidden.append(path)
    assert not forbidden
