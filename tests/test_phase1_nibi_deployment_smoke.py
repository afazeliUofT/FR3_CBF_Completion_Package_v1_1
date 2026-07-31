from __future__ import annotations

from datetime import datetime, timedelta, timezone
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "smoke_templates/phase1_nibi_deployment_smoke_v1"

METHOD_IDS = [
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
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def minimal_contract() -> dict:
    return {
        "execution_scope": "NONCAMPAIGN_SINGLE_SEED_SMOKE_ONLY",
        "smoke_seed": 43999,
        "confirmatory_seed_list": list(range(44000, 44030)),
        "job_package_id": "a" * 64,
        "job_package_sha256": "b" * 64,
        "candidate_v3_sha256": "c" * 64,
        "reviewed_job_package_commit": "d" * 40,
        "job_package_review_commit": "e" * 40,
        "full_campaign_execution_authorized": False,
        "merge_authorized": False,
    }


def test_config_uses_excluded_seed_and_single_job():
    value = json.loads(
        (
            ROOT / "config/phase1_nibi_deployment_smoke_v1.json"
        ).read_text(encoding="utf-8")
    )
    assert value["smoke"]["seed"] == 43999
    assert value["smoke"]["seed"] not in range(44000, 44030)
    assert value["smoke"]["excluded_from_confirmatory_analysis"] is True
    assert value["independent_review"][
        "full_campaign_execution_authorized"
    ] is False
    remote = (
        TEMPLATE / "remote_smoke_orchestrator.sh"
    ).read_text(encoding="utf-8")
    assert remote.count("sbatch") == 1
    assert "--array" not in remote
    assert "--gpus-per-node=h100:1" in remote


def test_token_is_environment_bound_and_smoke_scoped(tmp_path: Path):
    contract = tmp_path / "contract.json"
    env_lock = tmp_path / "environment.json"
    token = tmp_path / "token.json"
    contract.write_text(
        json.dumps(minimal_contract()) + "\n",
        encoding="utf-8",
    )
    env_lock.write_text('{"environment":"frozen"}\n', encoding="utf-8")
    subprocess.run(
        [
            sys.executable,
            str(TEMPLATE / "make_smoke_token.py"),
            "--contract",
            str(contract),
            "--environment-lock",
            str(env_lock),
            "--output",
            str(token),
            "--source-commit",
            "f" * 40,
            "--smoke-package-sha256",
            "1" * 64,
            "--ttl-hours",
            "24",
        ],
        check=True,
    )
    validator = load_module(
        "validate_smoke_token_test",
        TEMPLATE / "validate_smoke_token.py",
    )
    value = validator.validate(
        token,
        env_lock,
        contract,
        "f" * 40,
        "1" * 64,
    )
    assert value["smoke_seed"] == 43999
    assert value["full_campaign_execution_authorized"] is False
    assert value["campaign_array_authorized"] is False
    assert value["merge_authorized"] is False
    assert value["environment_lock_sha256"] == sha256_file(env_lock)


def test_expired_token_is_rejected(tmp_path: Path):
    contract = tmp_path / "contract.json"
    env_lock = tmp_path / "environment.json"
    token = tmp_path / "token.json"
    contract.write_text(
        json.dumps(minimal_contract()) + "\n",
        encoding="utf-8",
    )
    env_lock.write_text("{}\n", encoding="utf-8")
    now = datetime.now(timezone.utc)
    value = {
        "authorization": "EXECUTE_PHASE1_NIBI_DEPLOYMENT_SMOKE_V1",
        "execution_authorized": True,
        "execution_scope": "NONCAMPAIGN_SINGLE_SEED_SMOKE_ONLY",
        "stage": "NIBI_DEPLOYMENT_SMOKE",
        "smoke_seed": 43999,
        "excluded_from_phase1_confirmatory_analysis": True,
        "analysis_scope": "EXCLUDED_FROM_PHASE1_CONFIRMATORY_ANALYSIS",
        "full_campaign_execution_authorized": False,
        "campaign_array_authorized": False,
        "merge_authorized": False,
        "package_id": "a" * 64,
        "job_package_sha256": "b" * 64,
        "candidate_v3_sha256": "c" * 64,
        "reviewed_job_package_commit": "d" * 40,
        "job_package_review_commit": "e" * 40,
        "smoke_package_sha256": "1" * 64,
        "smoke_source_commit": "f" * 40,
        "environment_lock_sha256": sha256_file(env_lock),
        "issued_utc": (now - timedelta(hours=2)).isoformat(),
        "expires_utc": (now - timedelta(hours=1)).isoformat(),
        "allowed_job_count": 1,
        "allowed_slurm_array": False,
    }
    token.write_text(json.dumps(value) + "\n", encoding="utf-8")
    validator = load_module(
        "validate_smoke_token_expired_test",
        TEMPLATE / "validate_smoke_token.py",
    )
    try:
        validator.validate(token, env_lock, contract, "f" * 40, "1" * 64)
    except RuntimeError as exc:
        assert "not currently valid" in str(exc)
    else:
        raise AssertionError("expired smoke token was accepted")


def test_synthetic_smoke_result_validates(tmp_path: Path):
    result = tmp_path / "result"
    result.mkdir()
    contract = tmp_path / "contract.json"
    env_lock = tmp_path / "environment.json"
    token = tmp_path / "token.json"
    contract_value = minimal_contract()
    contract.write_text(
        json.dumps(contract_value) + "\n",
        encoding="utf-8",
    )
    env_lock.write_text('{"environment":"locked"}\n', encoding="utf-8")
    token.write_text('{"token":"smoke"}\n', encoding="utf-8")

    rows = []
    safe = {
        METHOD_IDS[0],
        METHOD_IDS[1],
        METHOD_IDS[2],
        METHOD_IDS[5],
        METHOD_IDS[6],
        METHOD_IDS[7],
    }
    for slot in range(5):
        for method in METHOD_IDS:
            rows.append(
                {
                    "pass_slot": slot,
                    "method_id": method,
                    "confirmatory_analysis_included": False,
                    "analysis_scope": (
                        "EXCLUDED_FROM_PHASE1_CONFIRMATORY_ANALYSIS"
                    ),
                    "protected_sample_count": 10,
                    "long_violation_seconds": (
                        0 if method in safe else 1
                    ),
                    "short_violation_seconds": 0,
                    "eligible_floor_violation_user_seconds": 0,
                    "final_moving_pf_utility": 1.0 + slot / 100.0,
                    "runtime_seconds": 1.0,
                }
            )
    cells = pd.DataFrame(rows)
    cells.to_csv(result / "CELL_SUMMARY.csv", index=False)
    pd.DataFrame(
        {
            "pass_slot": range(5),
            "predictive_minus_static_final_pf": np.full(5, 0.1),
            "smoke_seed": np.full(5, 43999),
            "confirmatory_analysis_included": np.full(5, False),
            "analysis_scope": np.full(
                5, "EXCLUDED_FROM_PHASE1_CONFIRMATORY_ANALYSIS"
            ),
        }
    ).to_csv(result / "PRIMARY_PAIRED_EFFECTS.csv", index=False)
    for slot in range(5):
        np.savez_compressed(
            result / f"PASS_{slot}_METHOD_TRACES.npz",
            method_ids=np.asarray(METHOD_IDS),
            interval_lengths=np.asarray([5, 5]),
        )
    channel = {
        "smoke_seed": 43999,
        "user_seed": 87998,
        "channel_seed": 87999,
        "confirmatory_analysis_included": False,
    }
    (result / "SMOKE_CHANNEL_FINGERPRINTS.json").write_text(
        json.dumps(channel) + "\n",
        encoding="utf-8",
    )
    audit = {
        "status": (
            "PASS_NONCAMPAIGN_NIBI_DEPLOYMENT_SMOKE_"
            "EXCLUDED_FROM_PHASE1_CONFIRMATORY_ANALYSIS"
        ),
        "deployment_smoke": True,
        "smoke_seed": 43999,
        "confirmatory_analysis_included": False,
        "analysis_scope": "EXCLUDED_FROM_PHASE1_CONFIRMATORY_ANALYSIS",
        "full_campaign_execution_authorized": False,
        "merge_authorized": False,
        "package_id": "a" * 64,
        "job_package_sha256": "b" * 64,
        "candidate_v3_sha256": "c" * 64,
        "environment_lock_sha256": sha256_file(env_lock),
        "authorization_token_sha256": sha256_file(token),
        "cell_count": 40,
        "method_ids": METHOD_IDS,
        "pass_audits": [{"pass_slot": i} for i in range(5)],
    }
    (result / "NONCAMPAIGN_SMOKE_RESULT.json").write_text(
        json.dumps(audit) + "\n",
        encoding="utf-8",
    )
    manifest = {}
    for path in sorted(result.iterdir()):
        if path.is_file():
            manifest[path.name] = {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
    (result / "SMOKE_RESULT_FILE_MANIFEST.json").write_text(
        json.dumps(manifest) + "\n",
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            str(TEMPLATE / "validate_noncampaign_smoke.py"),
            "--result-dir",
            str(result),
            "--smoke-contract",
            str(contract),
            "--environment-lock",
            str(env_lock),
            "--token",
            str(token),
        ],
        check=True,
    )


def test_owned_sources_parse():
    for path in ROOT.rglob("*.py"):
        if any(
            part in {"campaign", "evidence", ".venv"}
            for part in path.parts
        ):
            continue
        if (
            path.name.startswith("50_")
            or path.name == "test_phase1_nibi_deployment_smoke.py"
            or TEMPLATE in path.parents
        ):
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
