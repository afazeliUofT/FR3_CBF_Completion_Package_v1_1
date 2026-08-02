#!/usr/bin/env python3
"""Audit that the drop-in can execute only the excluded one-seed smoke."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.package_root).expanduser().resolve()
    contract = json.loads(
        (root / "config/FINAL_WORKER_SMOKE_CONTRACT.json").read_text(
            encoding="utf-8"
        )
    )
    remote = (
        root / "wrappers/REMOTE_ORCHESTRATE_V4_3_NIBI_FINAL_WORKER_SMOKE.sh"
    ).read_text(encoding="utf-8")
    worker = (root / "wrappers/NIBI_FINAL_WORKER_SMOKE_H100.sh").read_text(
        encoding="utf-8"
    )
    wsl = (
        root / "wrappers/RUN_V4_3_NIBI_FINAL_WORKER_SMOKE_FROM_WSL.sh"
    ).read_text(encoding="utf-8")
    issuer = (root / "scripts/issue_final_worker_smoke_authorization.py").read_text(
        encoding="utf-8"
    )
    combined = "\n".join([remote, worker, wsl, issuer])
    checks = {
        "excluded_seed_only": contract["authorization"]["allowed_seeds"] == [43999],
        "confirmatory_seeds_disjoint": 43999
        not in contract["authorization"]["confirmatory_seeds"],
        "full_campaign_not_authorized": contract["authorization"][
            "full_campaign_authorized"
        ]
        is False,
        "array_not_authorized": contract["authorization"][
            "slurm_array_authorized"
        ]
        is False,
        "merge_not_authorized": contract["authorization"]["merge_authorized"]
        is False,
        "one_job_only": contract["execution"]["one_job_only"] is True,
        "fresh_channel_required": contract["execution"][
            "channel_generation_required"
        ]
        is True
        and contract["execution"]["reuse_preserved_channel"] is False,
        "final_worker_exact": contract["execution"]["final_worker"]
        == "phase1_seed_worker.py",
        "no_slurm_array_option": "--array" not in remote,
        "no_merge_worker": "phase1_merge_worker" not in combined,
        "no_reuse_channel_argument": "--reuse-channel" not in worker,
        "single_h100_request": "--gpus-per-node=h100:1" in remote,
        "authorization_token_deleted": 'rm -f "$TOKEN"' in remote,
        "no_force_push": "--force" not in wsl and "push -f" not in wsl,
        "no_terminal_termination": "wsl.exe --terminate" not in combined
        and "shutdown.exe" not in combined,
        "information_exchange_not_certified": contract[
            "information_exchange_locality_certified"
        ]
        is False,
        "campaign_claim_boundary": contract["claim_boundary"].startswith(
            "EXCLUDED_FINAL_CAMPAIGN_WORKER_SMOKE"
        ),
        "token_not_packaged": contract["authorization"]["token_included"] is False,
        "issuer_one_seed_constant": "SMOKE_SEED = 43999" in issuer,
        "issuer_one_job": '"allowed_job_count": 1' in issuer,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"policy/scope audit failed: {failed}")
    value = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_EXCLUDED_ONE_SEED_SMOKE_POLICY_AND_SCOPE_AUDIT",
        "checks": checks,
        "campaign_seed": 43999,
        "confirmatory_seed_count": 30,
        "full_campaign_execution_authorized": False,
        "information_exchange_locality_certified": False,
    }
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("POLICY_AND_SCOPE_AUDIT=PASS")
    print("FULL_CAMPAIGN_EXECUTION_AUTHORIZED=NO")
    print("INFORMATION_EXCHANGE_LOCALITY_CERTIFIED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
