#!/usr/bin/env python3
"""Issue a short-lived external token for the exact frozen full campaign."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--job-package-root", required=True)
    p.add_argument("--authorization-contract", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--expiry-days", type=int, default=14)
    p.add_argument("--authorization-package-sha256", required=True)
    args = p.parse_args()
    root = Path(args.job_package_root).expanduser().resolve()
    decision = json.loads(Path(args.authorization_contract).read_text(encoding="utf-8"))
    job = json.loads((root / "JOB_PACKAGE_CONTRACT.json").read_text(encoding="utf-8"))
    if decision["campaign_execution_authorized_by_this_package"] is not True:
        raise RuntimeError("authorization decision is not affirmative")
    if decision["immutable_bindings"]["rorqual_r2_package_id"] != job["package_id"]:
        raise RuntimeError("authorization decision/package ID mismatch")
    if decision["authorization_is_limited_to"]["allowed_seeds"] != job["campaign_seed_list"]:
        raise RuntimeError("authorization decision/seed list mismatch")
    if args.expiry_days < 2 or args.expiry_days > 30:
        raise ValueError("expiry-days must be between 2 and 30")
    manifest_sha = sha256_file(root / "PACKAGE_MANIFEST.sha256")
    expiry = datetime.now(timezone.utc) + timedelta(days=args.expiry_days)
    token = {
        "schema_version": 3,
        "authorization": "EXECUTE_PHASE1_RORQUAL_V4_3_R2",
        "authorization_decision_id": decision["authorization_decision_id"],
        "authorization_package_sha256": args.authorization_package_sha256,
        "execution_authorized": True,
        "execution_stage": "FULL_30_SEED_CONFIRMATORY_CAMPAIGN",
        "package_id": job["package_id"],
        "package_manifest_sha256": manifest_sha,
        "candidate_source_manifest_sha256": job["candidate_v4_3"]["source_manifest_sha256"],
        "freeze_commit": job["freeze_commit"],
        "allowed_seeds": job["campaign_seed_list"],
        "authorization_expires_utc": expiry.isoformat(),
        "issued_utc": datetime.now(timezone.utc).isoformat(),
        "token_included_in_return": False,
    }
    out = Path(args.output).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(token, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(out, 0o600)

    sys.path.insert(0, str(root))
    os.environ["PHASE1_AUTHORIZATION_FILE"] = str(out)
    from authorization_guard import require_authorization
    verified = require_authorization(job)
    if verified["execution_stage"] != "FULL_30_SEED_CONFIRMATORY_CAMPAIGN":
        raise RuntimeError("native guard returned wrong stage")
    if verified["allowed_seeds"] != list(range(44000, 44030)):
        raise RuntimeError("native guard returned wrong seeds")

    print("FULL_CAMPAIGN_AUTHORIZATION_ISSUED=PASS")
    print("NATIVE_AUTHORIZATION_GUARD=PASS")
    print("AUTHORIZATION_DECISION_ID=" + decision["authorization_decision_id"])
    print("AUTHORIZATION_TOKEN_SHA256=" + sha256_file(out))
    print("AUTHORIZATION_EXPIRES_UTC=" + expiry.isoformat())
    print("AUTHORIZED_SEED_COUNT=30")
    print("AUTHORIZED_SEED_FIRST=44000")
    print("AUTHORIZED_SEED_LAST=44029")
    print("EXECUTION_STAGE=FULL_30_SEED_CONFIRMATORY_CAMPAIGN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
