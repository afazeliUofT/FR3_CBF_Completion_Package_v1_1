#!/usr/bin/env python3
"""Validate the smoke-only token against package and environment bindings."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_utc(value: str) -> datetime:
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def validate(
    token_path: Path,
    environment_lock_path: Path,
    contract_path: Path,
    source_commit: str,
    smoke_package_sha256: str,
) -> dict:
    token = json.loads(token_path.read_text(encoding="utf-8"))
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    required = {
        "authorization": "EXECUTE_PHASE1_NIBI_DEPLOYMENT_SMOKE_V1",
        "execution_authorized": True,
        "execution_scope": "NONCAMPAIGN_SINGLE_SEED_SMOKE_ONLY",
        "stage": "NIBI_DEPLOYMENT_SMOKE",
        "smoke_seed": int(contract["smoke_seed"]),
        "excluded_from_phase1_confirmatory_analysis": True,
        "analysis_scope": "EXCLUDED_FROM_PHASE1_CONFIRMATORY_ANALYSIS",
        "full_campaign_execution_authorized": False,
        "campaign_array_authorized": False,
        "merge_authorized": False,
        "package_id": contract["job_package_id"],
        "job_package_sha256": contract["job_package_sha256"],
        "candidate_v3_sha256": contract["candidate_v3_sha256"],
        "reviewed_job_package_commit": contract["reviewed_job_package_commit"],
        "job_package_review_commit": contract["job_package_review_commit"],
        "smoke_package_sha256": smoke_package_sha256,
        "smoke_source_commit": source_commit,
        "environment_lock_sha256": sha256_file(environment_lock_path),
        "allowed_job_count": 1,
        "allowed_slurm_array": False,
    }
    for key, expected in required.items():
        if token.get(key) != expected:
            raise RuntimeError(
                f"smoke token mismatch for {key}: "
                f"{token.get(key)!r} != {expected!r}"
            )
    if int(token["smoke_seed"]) in {
        int(value) for value in contract["confirmatory_seed_list"]
    }:
        raise RuntimeError("smoke token overlaps a confirmatory seed")
    now = datetime.now(timezone.utc)
    issued = parse_utc(token["issued_utc"])
    expires = parse_utc(token["expires_utc"])
    if not (issued <= now < expires):
        raise RuntimeError(
            f"smoke token is not currently valid: {issued=} {now=} {expires=}"
        )
    return token


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", required=True)
    parser.add_argument("--environment-lock", required=True)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--smoke-package-sha256", required=True)
    args = parser.parse_args()
    token_path = Path(args.token).expanduser().resolve()
    env_path = Path(args.environment_lock).expanduser().resolve()
    contract_path = Path(args.contract).expanduser().resolve()
    value = validate(
        token_path,
        env_path,
        contract_path,
        args.source_commit,
        args.smoke_package_sha256,
    )
    print("SMOKE AUTHORIZATION TOKEN VALIDATION: PASS")
    print(json.dumps(
        {
            "smoke_seed": value["smoke_seed"],
            "execution_scope": value["execution_scope"],
            "expires_utc": value["expires_utc"],
            "full_campaign_execution_authorized": False,
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
