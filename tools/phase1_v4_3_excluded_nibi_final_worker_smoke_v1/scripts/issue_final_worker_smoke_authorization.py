#!/usr/bin/env python3
"""Issue and validate one expiring authorization for excluded seed 43999 only."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path

SMOKE_STAGE = "EXCLUDED_FINAL_WORKER_SMOKE_SEED43999"
AUTHORIZATION = "EXECUTE_PHASE1_NIBI_V4_3_V1"
SMOKE_SEED = 43999


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_native_guard(job_root: Path):
    source = job_root / "authorization_guard.py"
    spec = importlib.util.spec_from_file_location("fr3_native_authorization_guard", source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load native authorization guard: {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--record-output", required=True)
    parser.add_argument("--ttl-hours", type=int, default=168)
    parser.add_argument("--smoke-source-commit", required=True)
    parser.add_argument("--smoke-package-sha256", required=True)
    args = parser.parse_args()

    job_root = Path(args.job_root).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    record_output = Path(args.record_output).expanduser().resolve()
    contract = json.loads(
        (job_root / "JOB_PACKAGE_CONTRACT.json").read_text(encoding="utf-8")
    )
    if int(contract["excluded_smoke_seed"]) != SMOKE_SEED:
        raise ValueError("locked job package excluded seed is not 43999")
    if SMOKE_SEED in {int(value) for value in contract["campaign_seed_list"]}:
        raise ValueError("excluded smoke seed overlaps confirmatory seeds")
    permitted = contract["authorization_contract"]["permitted_execution_stages"]
    if SMOKE_STAGE not in permitted:
        raise ValueError("locked job package does not permit the excluded smoke stage")
    if contract["execution_authorized"] is not False:
        raise ValueError("locked package unexpectedly claims execution authorization")
    ttl = int(args.ttl_hours)
    if not 1 <= ttl <= 168:
        raise ValueError("token TTL must be between 1 and 168 hours")

    package_manifest = job_root / "PACKAGE_MANIFEST.sha256"
    if not package_manifest.is_file():
        raise FileNotFoundError(package_manifest)
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(hours=ttl)
    value = {
        "schema_version": 1,
        "authorization": AUTHORIZATION,
        "package_id": contract["package_id"],
        "package_manifest_sha256": sha256_file(package_manifest),
        "candidate_source_manifest_sha256": contract["candidate_v4_3"][
            "source_manifest_sha256"
        ],
        "freeze_commit": contract["freeze_commit"],
        "execution_authorized": True,
        "execution_stage": SMOKE_STAGE,
        "allowed_seeds": [SMOKE_SEED],
        "authorization_expires_utc": expiry.isoformat(),
        "issued_utc": now.isoformat(),
        "excluded_from_confirmatory_analysis": True,
        "full_campaign_execution_authorized": False,
        "slurm_array_authorized": False,
        "merge_authorized": False,
        "allowed_job_count": 1,
        "smoke_source_commit": args.smoke_source_commit,
        "smoke_package_sha256": args.smoke_package_sha256,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output.chmod(0o600)

    previous = os.environ.get("PHASE1_AUTHORIZATION_FILE")
    os.environ["PHASE1_AUTHORIZATION_FILE"] = str(output)
    try:
        guard = load_native_guard(job_root)
        verified = guard.require_authorization(contract)
    finally:
        if previous is None:
            os.environ.pop("PHASE1_AUTHORIZATION_FILE", None)
        else:
            os.environ["PHASE1_AUTHORIZATION_FILE"] = previous

    if verified["execution_stage"] != SMOKE_STAGE:
        raise RuntimeError("native guard returned wrong execution stage")
    if verified["allowed_seeds"] != [SMOKE_SEED]:
        raise RuntimeError("native guard returned wrong seed scope")

    token_sha = sha256_file(output)
    record = {
        "schema_version": 1,
        "issued_utc": value["issued_utc"],
        "authorization_expires_utc": value["authorization_expires_utc"],
        "authorization_token_sha256": token_sha,
        "execution_stage": SMOKE_STAGE,
        "allowed_seeds": [SMOKE_SEED],
        "package_id": contract["package_id"],
        "package_manifest_sha256": value["package_manifest_sha256"],
        "candidate_source_manifest_sha256": value[
            "candidate_source_manifest_sha256"
        ],
        "freeze_commit": value["freeze_commit"],
        "smoke_source_commit": args.smoke_source_commit,
        "smoke_package_sha256": args.smoke_package_sha256,
        "native_authorization_guard": "PASS",
        "token_in_return_bundle": False,
        "full_campaign_execution_authorized": False,
        "slurm_array_authorized": False,
        "merge_authorized": False,
    }
    record_output.parent.mkdir(parents=True, exist_ok=True)
    record_output.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("FINAL_WORKER_SMOKE_AUTHORIZATION_ISSUED=PASS")
    print("NATIVE_AUTHORIZATION_GUARD=PASS")
    print(f"AUTHORIZATION_TOKEN_SHA256={token_sha}")
    print(f"AUTHORIZATION_EXPIRES_UTC={value['authorization_expires_utc']}")
    print("AUTHORIZED_SEED=43999")
    print("FULL_CAMPAIGN_EXECUTION_AUTHORIZED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
