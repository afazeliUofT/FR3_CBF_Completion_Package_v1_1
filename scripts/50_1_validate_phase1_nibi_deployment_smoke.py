#!/usr/bin/env python3
"""Strict validation of the reviewed noncampaign Nibi smoke package."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_manifest(root: Path, manifest: Path) -> int:
    count = 0
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        expected, relative = raw.split("  ", 1)
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        if sha256_file(path) != expected:
            raise ValueError(f"smoke source manifest mismatch: {relative}")
        count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="config/phase1_nibi_deployment_smoke_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    root = ROOT / cfg["paths"]["smoke_package_dir"]
    contract = json.loads(
        (root / "SMOKE_PACKAGE_CONTRACT.json").read_text(
            encoding="utf-8"
        )
    )
    review = json.loads(
        (root / "SMOKE_INDEPENDENT_REVIEW.json").read_text(
            encoding="utf-8"
        )
    )
    binding = json.loads(
        (root / "SMOKE_ZIP_BINDING.json").read_text(encoding="utf-8")
    )

    assert contract["status"] == (
        "REVIEWED_NONCAMPAIGN_NIBI_DEPLOYMENT_SMOKE_"
        "NOT_FULL_CAMPAIGN_EXECUTION"
    )
    assert contract["execution_scope"] == (
        "NONCAMPAIGN_SINGLE_SEED_SMOKE_ONLY"
    )
    assert contract["smoke_seed"] == 43999
    assert contract["smoke_seed"] not in contract[
        "confirmatory_seed_list"
    ]
    assert contract["user_seed"] == 87998
    assert contract["channel_seed"] == 87999
    assert contract["confirmatory_analysis_included"] is False
    assert contract["full_campaign_execution_authorized"] is False
    assert contract["campaign_array_authorized"] is False
    assert contract["merge_authorized"] is False
    assert review["verdict"] == (
        "PASS_FOR_SINGLE_NONCAMPAIGN_NIBI_DEPLOYMENT_SMOKE_"
        "EXECUTION_ONLY"
    )
    assert review["full_campaign_execution_authorized"] is False
    assert binding["smoke_package_id"] == contract["smoke_package_id"]
    assert binding["smoke_seed"] == contract["smoke_seed"]

    archive = root / "FR3_PHASE1_NIBI_DEPLOYMENT_SMOKE_v1.zip"
    checksum = Path(str(archive) + ".sha256")
    assert checksum.read_text(encoding="utf-8").split()[0] == sha256_file(
        archive
    )
    assert binding["zip_sha256"] == sha256_file(archive)
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        names = set(bundle.namelist())
        assert "SMOKE_PACKAGE_CONTRACT.json" in names
        assert "SMOKE_SOURCE_MANIFEST.sha256" in names
        assert "remote_smoke_orchestrator.sh" in names
        assert "smoke_h100_worker.sh" in names
        assert "run_noncampaign_smoke.py" in names
        assert "validate_noncampaign_smoke.py" in names

    manifest_count = verify_manifest(
        root, root / "SMOKE_SOURCE_MANIFEST.sha256"
    )
    assert manifest_count >= 10

    for path in root.rglob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for path in root.rglob("*.sh"):
        result = subprocess.run(
            ["bash", "-n", str(path)],
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(f"{path}: {result.stderr}")

    remote_text = (
        root / "remote_smoke_orchestrator.sh"
    ).read_text(encoding="utf-8")
    assert remote_text.count("sbatch") == 1
    assert "--array" not in remote_text
    assert "--gpus-per-node=h100:1" in remote_text
    assert "SMOKE_SEED" in remote_text
    assert "full_campaign_execution_authorized=NO" in remote_text

    worker_text = (root / "smoke_h100_worker.sh").read_text(
        encoding="utf-8"
    )
    assert "run_noncampaign_smoke.py" in worker_text
    assert "validate_noncampaign_smoke.py" in worker_text
    assert "PHASE1_SMOKE_PACKAGE_SHA256" in worker_text

    runner_text = (
        root / "run_noncampaign_smoke.py"
    ).read_text(encoding="utf-8")
    assert "EXCLUDED_FROM_PHASE1_CONFIRMATORY_ANALYSIS" in runner_text
    assert "worker.generate_channel(seed, channel_root)" in runner_text
    assert "for slot, pass_root in enumerate(pass_roots):" in runner_text
    assert "confirmatory_analysis_included" in runner_text

    token_text = (root / "make_smoke_token.py").read_text(
        encoding="utf-8"
    )
    assert "NONCAMPAIGN_SINGLE_SEED_SMOKE_ONLY" in token_text
    assert "full_campaign_execution_authorized" in token_text
    assert "merge_authorized" in token_text
    assert "environment_lock_sha256" in token_text
    assert "expires_utc" in token_text

    print("NONCAMPAIGN NIBI DEPLOYMENT SMOKE PACKAGE STRICT VALIDATION: PASS")
    print(json.dumps(
        {
            "smoke_package_id": contract["smoke_package_id"],
            "smoke_zip_sha256": sha256_file(archive),
            "source_manifest_entries": manifest_count,
            "smoke_seed": contract["smoke_seed"],
            "single_h100_job": True,
            "slurm_array": False,
            "full_campaign_execution_authorized": False,
            "next_gate": contract["next_gate"],
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
