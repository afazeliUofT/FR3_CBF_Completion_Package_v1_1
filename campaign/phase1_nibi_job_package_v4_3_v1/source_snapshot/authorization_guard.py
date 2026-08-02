"""Strict external authorization guard for the locked phase-1 package."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

FULL_STAGE = "FULL_30_SEED_CONFIRMATORY_CAMPAIGN"
SMOKE_STAGE = "EXCLUDED_FINAL_WORKER_SMOKE_SEED43999"
AUTHORIZATION_STRING = "EXECUTE_PHASE1_NIBI_V4_3_V1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _parse_future_expiry(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError("authorization_expires_utc is missing")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        expiry = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise RuntimeError("authorization_expires_utc is not valid ISO-8601") from exc
    if expiry.tzinfo is None:
        raise RuntimeError("authorization_expires_utc must include a UTC offset")
    expiry = expiry.astimezone(timezone.utc)
    if datetime.now(timezone.utc) >= expiry:
        raise RuntimeError("authorization token has expired")
    return expiry


def require_authorization(contract: dict[str, Any]) -> dict[str, Any]:
    """Validate a separately issued, exact-package-bound authorization file.

    The locked package contains only a non-authorizing template. A future token
    must bind the package ID, the full extracted-package manifest, the frozen
    candidate source manifest, the freeze commit, an exact execution stage, an
    exact seed list, and a future expiry.
    """
    auth_path = os.environ.get("PHASE1_AUTHORIZATION_FILE", "")
    if not auth_path:
        raise RuntimeError(
            "PHASE1_AUTHORIZATION_FILE is absent; package execution is locked"
        )
    path = Path(auth_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)

    package_root = Path(__file__).resolve().parent
    package_manifest = package_root / "PACKAGE_MANIFEST.sha256"
    if not package_manifest.is_file():
        raise FileNotFoundError(package_manifest)
    package_manifest_sha256 = sha256_file(package_manifest)

    value = json.loads(path.read_text(encoding="utf-8"))
    required_common = {
        "authorization": AUTHORIZATION_STRING,
        "package_id": contract["package_id"],
        "package_manifest_sha256": package_manifest_sha256,
        "candidate_source_manifest_sha256": contract["candidate_v4_3"][
            "source_manifest_sha256"
        ],
        "freeze_commit": contract["freeze_commit"],
        "execution_authorized": True,
    }
    for key, expected in required_common.items():
        if value.get(key) != expected:
            raise RuntimeError(
                f"authorization token mismatch for {key}: "
                f"{value.get(key)!r} != {expected!r}"
            )

    stage = value.get("execution_stage")
    if stage == FULL_STAGE:
        expected_seeds = contract["campaign_seed_list"]
    elif stage == SMOKE_STAGE:
        expected_seeds = [int(contract["excluded_smoke_seed"])]
    else:
        raise RuntimeError(f"unauthorized execution stage: {stage!r}")
    if value.get("allowed_seeds") != expected_seeds:
        raise RuntimeError(
            f"authorization seed list mismatch: {value.get('allowed_seeds')!r} "
            f"!= {expected_seeds!r}"
        )

    expiry = _parse_future_expiry(value.get("authorization_expires_utc"))
    value["authorization_expires_utc_normalized"] = expiry.isoformat()
    value["authorization_file_sha256"] = sha256_file(path)
    value["verified_package_manifest_sha256"] = package_manifest_sha256
    return value
