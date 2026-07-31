#!/usr/bin/env python3
"""Build the revised, execution-locked phase-1 candidate v3."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]

SOURCE_SNAPSHOT_PATHS = [
    "src/fr3_cbf/practical_architecture_mapping.py",
    "src/fr3_cbf/constrained_pf_safety.py",
    "src/fr3_cbf/robust_delayed_safety.py",
    "src/fr3_cbf/online_pf_load_transition.py",
    "src/fr3_cbf/dual_criterion_controller.py",
    "src/fr3_cbf/null_floor_aware_sector_backoff.py",
    "src/fr3_cbf/physical_impairment_sensitivity.py",
    "config/constrained_pf_controller_milestone_v1.json",
    "config/online_pf_load_transition_v1.json",
    "config/sector_selective_backoff_v1.json",
    "config/practical_architecture_mapping_v1.json",
    "config/phased_campaign_spec_v3.json",
    "docs/DELAYED_REACHABILITY_SAFETY_THEOREM.md",
    "docs/SECTOR_SELECTIVE_BACKOFF_CERTIFICATE.md",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_manifest(directory: Path, manifest_name: str) -> Path:
    manifest = directory / manifest_name
    lines = []
    for path in sorted(directory.rglob("*")):
        if (
            path.is_file()
            and path != manifest
            and not path.name.startswith(
                "FR3_PHASE1_CAMPAIGN_REVIEW_CANDIDATE_v3"
            )
        ):
            lines.append(
                f"{sha256_file(path)}  "
                f"{path.relative_to(directory).as_posix()}"
            )
    manifest.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    return manifest


def build_zip(directory: Path, output: Path) -> str:
    if output.exists():
        output.unlink()
    checksum = Path(str(output) + ".sha256")
    if checksum.exists():
        checksum.unlink()
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        allowZip64=True,
    ) as archive:
        for path in sorted(directory.rglob("*")):
            if (
                path.is_file()
                and path != output
                and path != checksum
            ):
                archive.write(
                    path,
                    path.relative_to(directory).as_posix(),
                )
    with zipfile.ZipFile(output) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError(f"corrupt candidate member: {bad}")
    digest = sha256_file(output)
    checksum.write_text(
        f"{digest}  {output.name}\n",
        encoding="utf-8",
    )
    return digest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        default="config/phase1_campaign_contract_v3.json",
    )
    args = parser.parse_args()

    contract_path = ROOT / args.contract
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    source_commit = contract["source_candidate_v2"]["commit"]

    candidate_v2 = ROOT / "campaign/phase1_candidate_v2"
    candidate_v3 = ROOT / "campaign/phase1_candidate_v3"
    if not candidate_v2.is_dir():
        raise NotADirectoryError(candidate_v2)

    v2_zip = (
        candidate_v2
        / "FR3_PHASE1_CAMPAIGN_REVIEW_CANDIDATE_v2.zip"
    )
    if sha256_file(v2_zip) != contract["source_candidate_v2"][
        "candidate_zip_sha256"
    ]:
        raise ValueError("candidate-v2 ZIP SHA-256 mismatch")

    if candidate_v3.exists():
        shutil.rmtree(candidate_v3)
    shutil.copytree(
        candidate_v2,
        candidate_v3,
        ignore=shutil.ignore_patterns(
            "FR3_PHASE1_CAMPAIGN_REVIEW_CANDIDATE_v2.zip",
            "FR3_PHASE1_CAMPAIGN_REVIEW_CANDIDATE_v2.zip.sha256",
            "BUNDLE_MANIFEST.sha256",
        ),
    )

    shutil.copy2(
        contract_path,
        candidate_v3 / "PHASE1_CAMPAIGN_CONTRACT_V3.json",
    )
    for relative in [
        "docs/PHASE1_INDEPENDENT_REVIEW_ROUND1.md",
        "docs/PHASE1_STATISTICAL_ANALYSIS_PLAN_V3.md",
        "docs/PHASE1_METHOD_INFORMATION_CONTRACT_V3.md",
    ]:
        shutil.copy2(
            ROOT / relative,
            candidate_v3 / Path(relative).name,
        )

    source_snapshot = candidate_v3 / "source_snapshot"
    source_records = []
    for relative in SOURCE_SNAPSHOT_PATHS:
        source = ROOT / relative
        if not source.is_file():
            raise FileNotFoundError(source)
        target = source_snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        source_records.append(
            {
                "path": relative,
                "sha256": sha256_file(source),
                "bytes": source.stat().st_size,
                "source_commit": source_commit,
            }
        )

    source_manifest = source_snapshot / "SOURCE_SNAPSHOT_MANIFEST.sha256"
    source_manifest.write_text(
        "\n".join(
            f"{row['sha256']}  {row['path']}"
            for row in source_records
        )
        + "\n",
        encoding="utf-8",
    )
    write_json(
        candidate_v3 / "SOURCE_SNAPSHOT_RECORD.json",
        {
            "schema_version": 1,
            "source_commit": source_commit,
            "files": source_records,
            "interpretation": (
                "Exact source/config snapshot for candidate review. "
                "The eventual job-array package must match these hashes "
                "or return to independent review."
            ),
        },
    )

    metadata_path = candidate_v3 / "CAMPAIGN_METADATA.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.update(
        {
            "schema_version": 3,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "candidate_v2_commit": source_commit,
            "candidate_v2_zip_sha256": contract[
                "source_candidate_v2"
            ]["candidate_zip_sha256"],
            "status": (
                "REVISED_COMPLETE_FIVE_PASS_REVIEW_CANDIDATE_V3_"
                "NOT_AUTHORIZED_FOR_EXECUTION"
            ),
            "execution_authorized": False,
            "independent_review_status": "PENDING_ROUND2",
            "primary_contract_file": (
                "PHASE1_CAMPAIGN_CONTRACT_V3.json"
            ),
            "primary_scenario": contract["primary_scenario"],
            "method_contracts": contract["method_contracts"],
            "statistics": contract["statistics"],
            "compute_dag": contract["compute_dag"],
            "stop_reasons": [
                "independent round-2 review has not returned PASS",
                "immutable job-array package is absent",
                "execution authorization token is absent",
            ],
            "next_gate": contract["next_gate"],
        }
    )
    write_json(metadata_path, metadata)

    write_json(
        candidate_v3 / "INDEPENDENT_REVIEW_STATUS.json",
        {
            "schema_version": 2,
            "status": "PENDING_ROUND2",
            "round1_verdict": "REQUIRES_REVISION",
            "round1_review_file": (
                "PHASE1_INDEPENDENT_REVIEW_ROUND1.md"
            ),
            "reviewer": None,
            "review_commit": None,
            "execution_authorized": False,
            "required_round2_checks": [
                "unique primary scenario and declared envelope",
                "method information/timing/fallback equivalence",
                "variable-pass-length load contract",
                "seed-cluster statistical analysis plan",
                "complete source/config snapshot",
                "compute DAG and no repeated channel generation",
                "all five immutable pass records",
                "execution locks and candidate provenance",
            ],
        },
    )
    (candidate_v3 / "EXECUTION_AUTHORIZED.txt").write_text(
        "FALSE\n",
        encoding="utf-8",
    )
    (candidate_v3 / "RUN_PHASE1_CAMPAIGN.sh").write_text(
        "#!/usr/bin/env bash\n"
        "set -Eeuo pipefail\n"
        "echo \"ERROR: phase-1 candidate v3 is not authorized for execution\"\n"
        "echo \"Missing: independent round-2 PASS, immutable job-array package, and authorization token\"\n"
        "exit 64\n",
        encoding="utf-8",
    )
    (candidate_v3 / "RUN_PHASE1_CAMPAIGN.sh").chmod(0o755)

    provenance = {
        "schema_version": 1,
        "candidate_v2_commit": source_commit,
        "candidate_v2_zip_sha256": contract[
            "source_candidate_v2"
        ]["candidate_zip_sha256"],
        "pass_record_commit": source_commit,
        "candidate_v3_build_commit": (
            "TO_BE_FILLED_BY_POST_COMMIT_REVIEW_RECORD"
        ),
        "source_snapshot_manifest_sha256": sha256_file(
            source_manifest
        ),
        "execution_authorized": False,
    }
    write_json(
        candidate_v3 / "CANDIDATE_PROVENANCE.json",
        provenance,
    )

    build_manifest(candidate_v3, "BUNDLE_MANIFEST.sha256")
    output = (
        candidate_v3
        / "FR3_PHASE1_CAMPAIGN_REVIEW_CANDIDATE_v3.zip"
    )
    digest = build_zip(candidate_v3, output)

    print("PHASE-1 CANDIDATE V3 BUILD: PASS")
    print("Candidate:", output)
    print("Candidate SHA-256:", digest)
    print("Execution authorized: NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
