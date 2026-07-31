#!/usr/bin/env python3
"""Build a complete five-pass but independently review-locked candidate."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="config/protected_pass_records_phase1_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    candidate_v1 = ROOT / cfg["input_candidates"][
        "phase1_candidate_v1"
    ][0]
    if not candidate_v1.is_dir():
        raise NotADirectoryError(candidate_v1)
    records = ROOT / cfg["paths"]["pass_records_dir"]
    record_index = json.loads(
        (records / "PASS_RECORD_INDEX.json").read_text(encoding="utf-8")
    )
    if not record_index["all_five_slots_ready"]:
        raise RuntimeError("all five pass records are not ready")

    candidate = ROOT / cfg["paths"]["phase1_candidate_v2_dir"]
    if candidate.exists():
        shutil.rmtree(candidate)
    shutil.copytree(
        candidate_v1,
        candidate,
        ignore=shutil.ignore_patterns(
            "FR3_PHASE1_CAMPAIGN_REVIEW_CANDIDATE_v1.zip",
            "FR3_PHASE1_CAMPAIGN_REVIEW_CANDIDATE_v1.zip.sha256",
            "BUNDLE_MANIFEST.sha256",
        ),
    )
    pass_dir = candidate / "protected_pass_records"
    pass_dir.mkdir(parents=True, exist_ok=True)
    slots = []
    for row in record_index["pass_slots"]:
        source_zip = records / row["record_zip"]
        source_sha = Path(str(source_zip) + ".sha256")
        shutil.copy2(source_zip, pass_dir / source_zip.name)
        shutil.copy2(source_sha, pass_dir / source_sha.name)
        slots.append(
            {
                "slot": row["slot"],
                "status": "IMMUTABLE_PASS_RECORD_READY",
                "record_zip": (
                    "protected_pass_records/" + source_zip.name
                ),
                "record_zip_sha256": row["record_zip_sha256"],
                "record_manifest_sha256": row[
                    "record_manifest_sha256"
                ],
                "selection": row["selection"],
                "protected_sample_count": row[
                    "protected_sample_count"
                ],
                "tle_age_days_at_peak": row[
                    "tle_age_days_at_peak"
                ],
                "tle_sha256": row["tle_sha256"],
            }
        )

    metadata_path = candidate / "CAMPAIGN_METADATA.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.update(
        {
            "schema_version": 2,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "source_commit_required": cfg["required_ancestor_commit"],
            "status": (
                "COMPLETE_FIVE_PASS_REVIEW_CANDIDATE_"
                "NOT_AUTHORIZED_FOR_EXECUTION"
            ),
            "execution_authorized": False,
            "independent_review_status": "PENDING",
            "protected_pass_slots": slots,
            "pass_selection_policy": cfg["selection_policy"],
            "stop_reasons": [
                "independent source review has not returned PASS",
                "execution authorization token is absent",
            ],
            "next_gate": cfg["next_gate"],
        }
    )
    write_json(metadata_path, metadata)
    (candidate / "EXECUTION_AUTHORIZED.txt").write_text(
        "FALSE\n",
        encoding="utf-8",
    )
    write_json(
        candidate / "INDEPENDENT_REVIEW_STATUS.json",
        {
            "schema_version": 1,
            "status": "PENDING",
            "reviewer": None,
            "review_commit": None,
            "execution_authorized": False,
            "required_checks": [
                "generic 64T64R grouping, phase convention and normalization",
                "local-RZF ranks and condition numbers",
                "exact safety and eligible-floor accounting",
                "sector-mute incidence and latency boundary",
                "paired method fairness and identical timing information",
                "all five pass records and their TLE/pattern/P.452 provenance",
                "campaign statistics and stop/go rules",
            ],
        },
    )
    (candidate / "RUN_PHASE1_CAMPAIGN.sh").write_text(
        "#!/usr/bin/env bash\n"
        "set -Eeuo pipefail\n"
        "echo \"ERROR: complete phase-1 candidate is not authorized for execution\"\n"
        "echo \"Missing: independent PASS and execution authorization token\"\n"
        "exit 64\n",
        encoding="utf-8",
    )
    (candidate / "RUN_PHASE1_CAMPAIGN.sh").chmod(0o755)

    protocol = candidate / "PHASE1_CAMPAIGN_REVIEW_PROTOCOL.md"
    protocol.write_text(
        protocol.read_text(encoding="utf-8")
        + "\n\n## Five-pass completion status\n\n"
        "All five immutable protected-pass records are now present. "
        "Execution remains blocked pending independent source review and "
        "an explicit authorization token.\n",
        encoding="utf-8",
    )

    manifest = candidate / "BUNDLE_MANIFEST.sha256"
    lines = []
    for path in sorted(candidate.rglob("*")):
        if (
            path.is_file()
            and path != manifest
            and not path.name.startswith(
                "FR3_PHASE1_CAMPAIGN_REVIEW_CANDIDATE_v2"
            )
        ):
            lines.append(
                f"{sha256_file(path)}  "
                f"{path.relative_to(candidate).as_posix()}"
            )
    manifest.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    output = (
        candidate / "FR3_PHASE1_CAMPAIGN_REVIEW_CANDIDATE_v2.zip"
    )
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        allowZip64=True,
    ) as archive:
        for path in sorted(candidate.rglob("*")):
            if (
                path.is_file()
                and path != output
                and path != Path(str(output) + ".sha256")
            ):
                archive.write(
                    path,
                    path.relative_to(candidate).as_posix(),
                )
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
    digest = sha256_file(output)
    Path(str(output) + ".sha256").write_text(
        f"{digest}  {output.name}\n",
        encoding="utf-8",
    )
    print("COMPLETE PHASE-1 CAMPAIGN REVIEW CANDIDATE: PASS")
    print("Candidate:", output)
    print("SHA-256:", digest)
    print("Execution authorized: NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
