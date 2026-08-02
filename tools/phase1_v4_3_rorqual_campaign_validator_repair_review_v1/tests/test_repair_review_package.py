from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def extract_smoke(temp: Path) -> Path:
    archive = ROOT / "immutable_bindings/FR3_RORQUAL_V4_3_FINAL_WORKER_SMOKE_43999_18132931.zip"
    with zipfile.ZipFile(archive) as zf:
        assert zf.testzip() is None
        zf.extractall(temp)
    roots = [p for p in temp.iterdir() if p.is_dir()]
    assert len(roots) == 1
    return roots[0]


def extract_legacy(temp: Path) -> Path:
    archive = ROOT / "immutable_bindings/locked_campaign/FR3_PHASE1_NIBI_JOB_PACKAGE_V4_3_v1.zip"
    with zipfile.ZipFile(archive) as zf:
        assert zf.testzip() is None
        zf.extractall(temp)
    return temp


def test_candidate_only_na_domain_is_intentional() -> None:
    module = load_module("validator_contract_test", ROOT / "templates/validator_contract.py")
    with tempfile.TemporaryDirectory() as name:
        smoke = extract_smoke(Path(name))
        cells = pd.read_csv(smoke / "result/CELL_SUMMARY.csv")
    audit = module.validate_cell_summary_numeric_domains(cells)
    assert audit["status"] == "PASS"
    assert audit["row_count"] == 45
    assert audit["candidate_row_count"] == 5
    assert audit["comparator_row_count"] == 40
    assert audit["intentional_candidate_only_na_count"] == 880


def test_common_numeric_nan_is_rejected() -> None:
    module = load_module("validator_contract_test_bad", ROOT / "templates/validator_contract.py")
    with tempfile.TemporaryDirectory() as name:
        smoke = extract_smoke(Path(name))
        cells = pd.read_csv(smoke / "result/CELL_SUMMARY.csv")
    cells.loc[0, "final_moving_pf_utility"] = np.nan
    with pytest.raises(ValueError, match="common numeric field"):
        module.validate_cell_summary_numeric_domains(cells)


def test_corrected_validator_passes_exact_smoke() -> None:
    with tempfile.TemporaryDirectory() as name:
        temp = Path(name)
        smoke = extract_smoke(temp / "smoke")
        legacy = extract_legacy(temp / "legacy")
        validator_dir = temp / "validator"
        validator_dir.mkdir()
        for source in [
            ROOT / "templates/validate_seed_result.py",
            ROOT / "templates/validator_contract.py",
        ]:
            (validator_dir / source.name).write_bytes(source.read_bytes())
        completed = subprocess.run(
            [
                sys.executable,
                str(validator_dir / "validate_seed_result.py"),
                "--result-dir",
                str(smoke / "result"),
                "--package-contract",
                str(legacy / "JOB_PACKAGE_CONTRACT.json"),
                "--require-scientific-pass",
            ],
            text=True,
            capture_output=True,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert "CELL_SUMMARY_NUMERIC_DOMAIN_GATE=PASS" in completed.stdout


def test_geometric_mean_definitions_explain_exact_mismatch() -> None:
    reference = ROOT / "immutable_bindings/reference_seed43999"
    utility = pd.read_csv(reference / "REFERENCE_CANDIDATE_UTILITY_SUMMARY.csv")
    with tempfile.TemporaryDirectory() as name:
        smoke = extract_smoke(Path(name))
        cells = pd.read_csv(smoke / "result/CELL_SUMMARY.csv")
    candidate = cells.loc[
        cells["method_id"] == "candidate_v4_3_floor_feasibility_repair"
    ].sort_values("pass_slot")
    differences = []
    alpha = 1.0 - np.exp(-5.0 / 100.0)
    for slot in range(5):
        with np.load(reference / f"REFERENCE_CANDIDATE_PASS_{slot}_TRACE.npz") as z:
            initial = (z["candidate_moving_average_rate"][0] - alpha * z["candidate_total_rate"][0]) / (1.0 - alpha)
            eligible = initial >= 0.1
            values = np.concatenate([row[eligible][row[eligible] > 0] for row in z["candidate_total_rate"]])
        standard = float(np.exp(np.mean(np.log(values))))
        stabilized = float(np.exp(np.mean(np.log(values + 0.001))) - 0.001)
        actual = float(candidate.loc[candidate["pass_slot"] == slot, "total_active_eligible_geometric_mean_bps_hz"].iloc[0])
        frozen = float(utility.loc[utility["pass_slot"] == slot, "candidate_total_active_eligible_geometric_mean_bps_hz"].iloc[0])
        assert abs(actual - stabilized) <= 1e-12
        assert abs(frozen - standard) <= 1e-12
        differences.append(stabilized - standard)
    assert max(differences) == pytest.approx(0.0007817331170665298, abs=1e-15)


def test_full_local_repair_build_and_review() -> None:
    with tempfile.TemporaryDirectory() as name:
        temp = Path(name)
        audit = temp / "audit"
        build = temp / "build"
        review = temp / "review"
        for command in [
            [sys.executable, str(ROOT / "scripts/audit_and_reclassify_smoke.py"), "--output-root", str(audit)],
            [sys.executable, str(ROOT / "scripts/build_rorqual_campaign_package.py"), "--audit-root", str(audit), "--output-root", str(build)],
            [sys.executable, str(ROOT / "scripts/independent_review_rorqual_campaign.py"), "--audit-root", str(audit), "--build-root", str(build), "--output-root", str(review)],
        ]:
            completed = subprocess.run(command, text=True, capture_output=True)
            assert completed.returncode == 0, completed.stdout + completed.stderr
        verdict = json.loads((review / "INDEPENDENT_REVIEW_VERDICT.json").read_text())
        assert verdict["status"].startswith("PASS_CORRECTED_RORQUAL_NATIVE")
        assert verdict["campaign_execution_authorized"] is False
        job = build / "FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2.zip"
        with zipfile.ZipFile(job) as zf:
            assert zf.testzip() is None
            names = set(zf.namelist())
            assert "RUN_PHASE1_RORQUAL_CAMPAIGN.sh" in names
            assert "RUN_PHASE1_NIBI_CAMPAIGN.sh" not in names


def test_workflow_is_local_only_and_execution_locked() -> None:
    wrapper = (ROOT / "wrappers/RUN_V4_3_RORQUAL_CAMPAIGN_REPAIR_REVIEW_FROM_WSL.sh").read_text()
    assert "ssh " not in wrapper
    assert "scp " not in wrapper
    assert "CLUSTER_CONTACTED=NO" in wrapper
    assert "CAMPAIGN_EXECUTION_AUTHORIZED=NO" in wrapper
    contract = json.loads((ROOT / "config/REPAIR_REVIEW_CONTRACT.json").read_text())
    assert contract["campaign_execution_authorized"] is False
    assert contract["cluster_contacted"] is False
