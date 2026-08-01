from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "immutable_bindings/v4_3_cpu_return"
EXPECTED_RETURN_SHA = "52fbd777e7816320f5bf05ed39ff6c3dd62573776336e404f1f2306875d98e90"
EXPECTED_SOURCE = "b65dc117f1ace492b55bd764f74bf985fbcb9507"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        text=True,
        capture_output=True,
        check=True,
        env={"PYTHONDONTWRITEBYTECODE": "1"},
    )


def test_contract_is_single_excluded_smoke_only() -> None:
    contract = json.loads((ROOT / "config/H100_DEPLOYMENT_SMOKE_CONTRACT.json").read_text())
    assert contract["excluded_seed"] == 43999
    assert contract["allowed_job_count"] == 1
    assert contract["confirmatory_campaign_authorized"] is False
    assert contract["channel_regeneration_allowed"] is False
    assert contract["candidate_cpu_return_sha256"] == EXPECTED_RETURN_SHA
    assert contract["candidate_source_commit"] == EXPECTED_SOURCE
    assert contract["controller_replay_execution"] == "CPU_NUMPY_SCIPY_HIGHS_ON_H100_NODE"


def test_independent_review_reproduces_frozen_pass(tmp_path: Path) -> None:
    output_json = tmp_path / "review.json"
    output_env = tmp_path / "review.env"
    result = run(
        str(ROOT / "scripts/independent_review_v4_3.py"),
        "--evidence-root",
        str(EVIDENCE),
        "--binding",
        str(ROOT / "immutable_bindings/V4_3_RETURN_BINDING.json"),
        "--output-json",
        str(output_json),
        "--output-env",
        str(output_env),
    )
    review = json.loads(output_json.read_text())
    assert review["review_status"] == "PASS_TO_SINGLE_EXCLUDED_H100_DEPLOYMENT_SMOKE"
    assert review["source_supported_facts"]["floor_violation_user_seconds"] == 0
    assert review["source_supported_facts"]["repair_intervals"] == 104
    assert review["source_supported_facts"]["repair_physical_seconds"] == 519
    assert review["source_supported_facts"]["action_class_counts"] == {
        "BASELINE_NOOP": 486,
        "SPARSE_LOCAL_FROZEN_GRID_SECTOR_REPAIR": 6,
        "SPARSE_LOCAL_STREAM_POWER_REPAIR": 98,
    }
    assert "INDEPENDENT_V4_3_REVIEW=PASS" in result.stdout
    assert "CONFIRMATORY_CAMPAIGN_AUTHORIZED=NO" in output_env.read_text()


def test_h100_auditor_self_replay_exact_data(tmp_path: Path) -> None:
    environment = tmp_path / "environment.json"
    environment.write_text(
        json.dumps(
            {
                "status": "PASS_H100_ENVIRONMENT_AND_PRESERVED_CHANNEL_ACCESS",
                "channel_regenerated": False,
                "controller_replay_execution": "CPU_NUMPY_SCIPY_HIGHS_ON_H100_NODE",
                "gpu_name": "NVIDIA H100 80GB HBM3",
                "confirmatory_campaign_authorized": False,
            }
        )
        + "\n"
    )
    output_json = tmp_path / "audit.json"
    output_env = tmp_path / "audit.env"
    utility = tmp_path / "utility.csv"
    result = run(
        str(ROOT / "scripts/audit_h100_deployment_smoke.py"),
        "--cpu-summary",
        str(EVIDENCE / "summary"),
        "--h100-summary",
        str(EVIDENCE / "summary"),
        "--h100-environment",
        str(environment),
        "--output-json",
        str(output_json),
        "--output-env",
        str(output_env),
        "--utility-csv",
        str(utility),
    )
    audit = json.loads(output_json.read_text())
    assert audit["status"] == "PASS_EXCLUDED_H100_DEPLOYMENT_SMOKE_V4_3"
    assert audit["cpu_h100_trace_comparison"]["action_class_trace_exact"] is True
    assert max(audit["cpu_h100_trace_comparison"]["maximum_absolute_difference_by_array"].values()) == 0.0
    assert audit["confirmatory_campaign_authorized"] is False
    assert len(pd.read_csv(utility)) == 5
    assert "H100_CPU_TRACE_REPRODUCTION_GATE=PASS" in result.stdout


def test_return_packager_success_and_manifest(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    (run_root / "summary").mkdir(parents=True)
    (run_root / "summary/RUN_STATUS.env").write_text(
        "CANDIDATE_STATUS=PASS\nCONFIRMATORY_CAMPAIGN_AUTHORIZED=NO\n"
    )
    (run_root / "H100_ENVIRONMENT.json").write_text("{}\n")
    (run_root / "H100_DEPLOYMENT_SMOKE_STATUS.env").write_text(
        "H100_DEPLOYMENT_SMOKE_STATUS=PASS_EXCLUDED_H100_DEPLOYMENT_SMOKE_V4_3\n"
    )
    output = tmp_path / "return.zip"
    run(
        str(ROOT / "scripts/package_h100_return.py"),
        "--run-root",
        str(run_root),
        "--payload-root",
        str(ROOT),
        "--output",
        str(output),
        "--mode",
        "PASS",
        "--wrapper-exit",
        "0",
        "--job-id",
        "123",
        "--account",
        "def-rsadve_gpu",
        "--state",
        "COMPLETED",
        "--slurm-exit",
        "0:0",
        "--maxrss",
        "432072K",
        "--candidate-exit",
        "0",
        "--audit-exit",
        "0",
        "--source-commit",
        EXPECTED_SOURCE,
    )
    assert output.is_file()
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        assert "RETURN_METADATA.json" in names
        assert "RETURN_CONTENT_MANIFEST.sha256" in names
        assert "package/scripts/audit_h100_deployment_smoke.py" in names
        metadata = json.loads(archive.read("RETURN_METADATA.json"))
        assert metadata["status"] == "PASS_RETURN_READY"
        assert metadata["confirmatory_campaign_authorized"] is False
        manifest = archive.read("RETURN_CONTENT_MANIFEST.sha256").decode().splitlines()
        for line in manifest:
            digest, name = line.split(maxsplit=1)
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest


def test_no_compiled_or_cache_artifacts_in_source_tree() -> None:
    forbidden = []
    for path in ROOT.rglob("*"):
        if path.name in {"__pycache__", ".pytest_cache"} or path.suffix in {".pyc", ".pyo"}:
            forbidden.append(path)
    assert forbidden == []
