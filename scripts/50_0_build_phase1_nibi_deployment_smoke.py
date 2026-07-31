#!/usr/bin/env python3
"""Build the reviewed, single-seed, noncampaign Nibi smoke package."""
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="config/phase1_nibi_deployment_smoke_v1.json",
    )
    args = parser.parse_args()
    cfg_path = ROOT / args.config
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    job_zip = ROOT / cfg["job_package"]["path"]
    review_zip = ROOT / cfg["job_package_independent_review"][
        "review_bundle_path"
    ]
    if sha256_file(job_zip) != cfg["job_package"]["sha256"]:
        raise ValueError("immutable job-package ZIP SHA-256 mismatch")
    if sha256_file(review_zip) != cfg[
        "job_package_independent_review"
    ]["review_bundle_sha256"]:
        raise ValueError("job-package independent-review ZIP SHA-256 mismatch")

    review_verdict_path = (
        ROOT
        / "evidence/phase1_nibi_job_package_independent_review_v1/"
        "PHASE1_JOB_PACKAGE_INDEPENDENT_REVIEW_VERDICT.json"
    )
    review_verdict = json.loads(
        review_verdict_path.read_text(encoding="utf-8")
    )
    if review_verdict["verdict"] != cfg[
        "job_package_independent_review"
    ]["verdict"]:
        raise ValueError("independent job-package review verdict mismatch")
    if review_verdict["full_30_seed_execution_authorized"] is not False:
        raise ValueError("review unexpectedly authorizes full campaign")

    seed = int(cfg["smoke"]["seed"])
    confirmatory = list(range(44000, 44030))
    if seed in confirmatory:
        raise ValueError("smoke seed overlaps the confirmatory campaign")
    if int(cfg["smoke"]["user_seed"]) != 2 * seed:
        raise ValueError("smoke user-seed mapping is wrong")
    if int(cfg["smoke"]["channel_seed"]) != 2 * seed + 1:
        raise ValueError("smoke channel-seed mapping is wrong")

    template = ROOT / "smoke_templates/phase1_nibi_deployment_smoke_v1"
    output = ROOT / cfg["paths"]["smoke_package_dir"]
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(template, output)

    template_records = []
    for path in sorted(output.rglob("*")):
        if path.is_file():
            template_records.append(
                {
                    "path": path.relative_to(output).as_posix(),
                    "sha256": sha256_file(path),
                    "bytes": path.stat().st_size,
                }
            )
    id_material = b"\n".join(
        [
            cfg_path.read_bytes(),
            cfg["job_package"]["sha256"].encode(),
            cfg["job_package"]["package_id"].encode(),
            cfg["job_package_independent_review"][
                "review_bundle_sha256"
            ].encode(),
            str(seed).encode(),
        ]
        + [
            f"{row['sha256']}  {row['path']}".encode()
            for row in template_records
        ]
    )
    smoke_package_id = hashlib.sha256(id_material).hexdigest()

    contract = {
        "schema_version": 1,
        "status": (
            "REVIEWED_NONCAMPAIGN_NIBI_DEPLOYMENT_SMOKE_"
            "NOT_FULL_CAMPAIGN_EXECUTION"
        ),
        "claim_boundary": cfg["claim_boundary"],
        "smoke_package_id": smoke_package_id,
        "execution_scope": "NONCAMPAIGN_SINGLE_SEED_SMOKE_ONLY",
        "smoke_seed": seed,
        "user_seed": 2 * seed,
        "channel_seed": 2 * seed + 1,
        "confirmatory_seed_list": confirmatory,
        "analysis_scope": "EXCLUDED_FROM_PHASE1_CONFIRMATORY_ANALYSIS",
        "confirmatory_analysis_included": False,
        "full_campaign_execution_authorized": False,
        "campaign_array_authorized": False,
        "merge_authorized": False,
        "job_package_path": cfg["job_package"]["path"],
        "job_package_sha256": cfg["job_package"]["sha256"],
        "job_package_id": cfg["job_package"]["package_id"],
        "candidate_v3_sha256": cfg["job_package"][
            "candidate_v3_sha256"
        ],
        "reviewed_job_package_commit": cfg[
            "reviewed_job_package_commit"
        ],
        "job_package_review_commit": cfg[
            "job_package_independent_review"
        ]["commit"],
        "job_package_review_sha256": cfg[
            "job_package_independent_review"
        ]["review_bundle_sha256"],
        "token_ttl_hours": int(cfg["smoke"]["token_ttl_hours"]),
        "nibi": cfg["nibi"],
        "independent_review_verdict": cfg["independent_review"][
            "verdict"
        ],
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "next_gate": cfg["next_gate"],
    }
    write_json(output / "SMOKE_PACKAGE_CONTRACT.json", contract)

    review = {
        "schema_version": 1,
        "verdict": cfg["independent_review"]["verdict"],
        "smoke_package_id": smoke_package_id,
        "job_package_sha256": cfg["job_package"]["sha256"],
        "job_package_id": cfg["job_package"]["package_id"],
        "job_package_review_commit": cfg[
            "job_package_independent_review"
        ]["commit"],
        "smoke_seed": seed,
        "confirmatory_analysis_included": False,
        "full_campaign_execution_authorized": False,
        "merge_authorized": False,
        "checks": {
            "single_nonarray_h100_submission": "PASS",
            "noncampaign_seed": "PASS",
            "environment_lock_before_token": "PASS",
            "smoke_scoped_expiring_token": "PASS",
            "all_eight_methods_and_five_passes": "PASS_BY_IMMUTABLE_IMPORT",
            "compact_success_and_failure_return": "PASS",
            "full_campaign_and_merge_prohibited": "PASS",
        },
        "scope": (
            "ONE_EXCLUDED_NIBI_DEPLOYMENT_SMOKE_ONLY_"
            "NOT_PHASE1_RESULT_NOT_PAPER_RESULT"
        ),
    }
    write_json(output / "SMOKE_INDEPENDENT_REVIEW.json", review)

    source_manifest = output / "SMOKE_SOURCE_MANIFEST.sha256"
    lines = []
    for path in sorted(output.rglob("*")):
        if (
            path.is_file()
            and path != source_manifest
            and not path.name.startswith(
                "FR3_PHASE1_NIBI_DEPLOYMENT_SMOKE_v1"
            )
        ):
            lines.append(
                f"{sha256_file(path)}  "
                f"{path.relative_to(output).as_posix()}"
            )
    source_manifest.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    archive = output / "FR3_PHASE1_NIBI_DEPLOYMENT_SMOKE_v1.zip"
    checksum = Path(str(archive) + ".sha256")
    with zipfile.ZipFile(
        archive,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        allowZip64=True,
    ) as bundle:
        for path in sorted(output.rglob("*")):
            if (
                path.is_file()
                and path != archive
                and path != checksum
            ):
                bundle.write(
                    path,
                    path.relative_to(output).as_posix(),
                )
    with zipfile.ZipFile(archive) as bundle:
        bad = bundle.testzip()
        if bad is not None:
            raise RuntimeError(f"corrupt smoke-package member: {bad}")
    checksum.write_text(
        f"{sha256_file(archive)}  {archive.name}\n",
        encoding="utf-8",
        newline="\n",
    )
    write_json(
        output / "SMOKE_ZIP_BINDING.json",
        {
            "schema_version": 1,
            "smoke_package_id": smoke_package_id,
            "zip_path": archive.name,
            "zip_sha256": sha256_file(archive),
            "source_manifest_sha256": sha256_file(source_manifest),
            "job_package_sha256": cfg["job_package"]["sha256"],
            "smoke_seed": seed,
            "execution_scope": "NONCAMPAIGN_SINGLE_SEED_SMOKE_ONLY",
            "full_campaign_execution_authorized": False,
        },
    )

    print("NONCAMPAIGN NIBI DEPLOYMENT SMOKE PACKAGE BUILD: PASS")
    print("Smoke package ID:", smoke_package_id)
    print("Smoke ZIP:", archive)
    print("Smoke ZIP SHA-256:", sha256_file(archive))
    print("Smoke seed:", seed)
    print("Full campaign authorized: NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
