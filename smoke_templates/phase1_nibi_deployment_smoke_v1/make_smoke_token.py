#!/usr/bin/env python3
"""Create a narrowly scoped, expiring deployment-smoke authorization token."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True)
    parser.add_argument("--environment-lock", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--smoke-package-sha256", required=True)
    parser.add_argument("--ttl-hours", type=int, default=24)
    args = parser.parse_args()

    contract = json.loads(Path(args.contract).read_text(encoding="utf-8"))
    env_lock = Path(args.environment_lock).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(hours=int(args.ttl_hours))

    if contract["execution_scope"] != "NONCAMPAIGN_SINGLE_SEED_SMOKE_ONLY":
        raise ValueError("smoke contract has the wrong execution scope")
    if contract["smoke_seed"] in contract["confirmatory_seed_list"]:
        raise ValueError("smoke seed overlaps the confirmatory seed list")

    value = {
        "schema_version": 1,
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
        "smoke_package_sha256": args.smoke_package_sha256,
        "smoke_source_commit": args.source_commit,
        "environment_lock_sha256": sha256_file(env_lock),
        "issued_utc": now.isoformat(),
        "expires_utc": expiry.isoformat(),
        "allowed_job_count": 1,
        "allowed_slurm_array": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    Path(str(output) + ".sha256").write_text(
        f"{sha256_file(output)}  {output.name}\n",
        encoding="utf-8",
        newline="\n",
    )
    print("SMOKE-SCOPED AUTHORIZATION TOKEN: PASS")
    print("Token:", output)
    print("Token SHA-256:", sha256_file(output))
    print("Expires UTC:", value["expires_utc"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
