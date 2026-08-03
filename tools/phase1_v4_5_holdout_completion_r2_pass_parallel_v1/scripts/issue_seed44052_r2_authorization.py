#!/usr/bin/env python3
"""Issue one short-lived authorization for the pass-parallel seed-44052 completion."""
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
    p.add_argument("--completion-contract", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    root = Path(args.job_package_root).resolve()
    completion = json.loads(Path(args.completion_contract).read_text(encoding="utf-8"))
    job = json.loads((root / "JOB_PACKAGE_CONTRACT.json").read_text(encoding="utf-8"))
    if completion["existing_holdout_package_id"] != job["package_id"]:
        raise RuntimeError("completion/original package ID mismatch")
    if completion["seed"] != 44052 or completion["pass_slots"] != [0, 1, 2, 3, 4]:
        raise RuntimeError("R2 scope is not exactly seed 44052 and passes 0-4")
    expiry = datetime.now(timezone.utc) + timedelta(hours=12)
    token = {
        "schema_version": 1,
        "authorization": "EXECUTE_FRESH_V4_5_HOLDOUT_RORQUAL_V1",
        "authorization_package_sha256": "HOLDOUT_COMPLETION_R2_PASS_PARALLEL",
        "execution_authorized": True,
        "execution_stage": "FRESH_V4_5_HOLDOUT_30_SEED",
        "package_id": job["package_id"],
        "package_manifest_sha256": sha256_file(root / "PACKAGE_MANIFEST.sha256"),
        "candidate_source_manifest_sha256": job["candidate_v4_5"]["source_manifest_sha256"],
        "freeze_commit": job["freeze_commit"],
        "allowed_seeds": job["campaign_seed_list"],
        "authorization_expires_utc": expiry.isoformat(),
        "issued_utc": datetime.now(timezone.utc).isoformat(),
        "token_included_in_return": False,
        "execution_wrapper_restriction": "RUN_ONLY_SEED_44052_PASSES_0_TO_4_REUSE_EXISTING_CHANNEL",
        "automatic_extra_seed_or_algorithm_tuning_authorized": False,
    }
    out = Path(args.output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(token, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(out, 0o600)

    sys.path.insert(0, str(root))
    os.environ["PHASE1_AUTHORIZATION_FILE"] = str(out)
    from authorization_guard import require_authorization

    verified = require_authorization(job)
    if 44052 not in verified["allowed_seeds"]:
        raise RuntimeError("native guard did not authorize seed 44052")
    print("SEED44052_R2_AUTHORIZATION_ISSUED=PASS")
    print("NATIVE_AUTHORIZATION_GUARD=PASS")
    print("AUTHORIZED_EXECUTION_WRAPPER_SCOPE=SEED_44052_PASSES_0_TO_4_ONLY")
    print("AUTHORIZATION_TOKEN_SHA256=" + sha256_file(out))
    print("AUTHORIZATION_EXPIRES_UTC=" + expiry.isoformat())
    print("AUTOMATIC_EXTRA_SEEDS_AUTHORIZED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
