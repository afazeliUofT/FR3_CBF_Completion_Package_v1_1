#!/usr/bin/env python3
"""Build an immutable, deliberately non-executable phase-1 review candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="config/practical_architecture_mapping_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    results = ROOT / cfg["paths"]["results_dir"]
    evidence = ROOT / cfg["paths"]["evidence_dir"]
    gate = json.loads(
        (evidence / "ARCHITECTURE_GATE_DECISION.json").read_text(
            encoding="utf-8"
        )
    )
    if gate["status"] != (
        "PASS_GENERIC_64T64R_ARCHITECTURE_MAPPING_ONE_SEED"
    ):
        raise ValueError("architecture gate did not pass")

    output = ROOT / cfg["paths"]["campaign_candidate_dir"]
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    metadata = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "REVIEW_CANDIDATE_NOT_AUTHORIZED_FOR_EXECUTION",
        "execution_authorized": False,
        "source_commit_required": cfg["required_ancestor_commit"],
        "selected_architecture": gate[
            "selected_phase1_primary_architecture"
        ],
        "architecture_claim_boundary": cfg["claim_boundary"],
        "phase1_replication_units": 150,
        "channel_topology_seeds": list(range(44000, 44030)),
        "protected_pass_slots": [
            {
                "slot": 0,
                "status": "CURRENT_VALIDATED_PASS",
                "source_h100_job_id": "18696267",
                "validation_cpu_job_id": "18704028",
                "full_return_sha256": (
                    "e9ac40e3839e9c5ff6e0fdc9a13145af988a9cfd1b2fbcb48368845e7b9aa42a"
                ),
                "compact_review_sha256": (
                    "b1c2dd5866b1b39b7336e1adba1255b8374ddf10d9b8509e349e7802b5c7c1bf"
                ),
            },
            *[
                {
                    "slot": slot,
                    "status": "MISSING_IMMUTABLE_PASS_RECORD",
                }
                for slot in range(1, 5)
            ],
        ],
        "primary_design": {
            "pattern": "SA.509 multiple-entry primary",
            "criterion": (
                "joint long-term design with separately reported "
                "short-term verification"
            ),
            "declared_array_sensitivity": {
                "null_depth_cap_db": [60, 65, 67],
                "residual_coupling_uplift_db": [0, 1, 3],
            },
            "load": "staggered arrivals/departures plus deterministic stress",
            "delay_intervals": 1,
            "slew_db_per_update": 3,
            "update_interval_s": 5,
        },
        "paired_methods": [
            "robust_predictive_constrained_pf_with_sector_selective_fallback",
            "static_robust_constrained_pf",
            "delayed_myopic_constrained_pf",
            "virtual_queue",
            "uniform_protected_tone_backoff",
            "hard_spatial_null",
            "common_scale_oracle_upper_reference",
        ],
        "primary_endpoints": [
            "hard-safety violation count and maximum excess",
            "moving-average constrained-PF utility",
            "eligible-floor violation user-seconds",
            "protected-band p05 and geometric-mean rate",
        ],
        "statistics": {
            "paired_comparisons": True,
            "confidence_level": 0.95,
            "bootstrap": "clustered by channel/topology seed and protected pass",
        },
        "stop_reasons": [
            "four protected-pass records are missing",
            "independent source review has not returned PASS",
            "execution authorization token is absent",
        ],
        "next_gate": cfg["next_gate"],
    }
    (output / "CAMPAIGN_METADATA.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "EXECUTION_AUTHORIZED.txt").write_text(
        "FALSE\n",
        encoding="utf-8",
    )
    runner = output / "RUN_PHASE1_CAMPAIGN.sh"
    runner.write_text(
        "#!/usr/bin/env bash\n"
        "set -Eeuo pipefail\n"
        'echo "ERROR: phase-1 campaign candidate is not authorized for execution"\n'
        'echo "Missing: four protected-pass records and independent review"\n'
        "exit 64\n",
        encoding="utf-8",
    )
    runner.chmod(0o755)

    copies = {
        ROOT / "config/practical_architecture_mapping_v1.json": (
            output / "PRACTICAL_ARCHITECTURE_MAPPING_CONFIG.json"
        ),
        results / "ARCHITECTURE_CASE_SUMMARY.csv": (
            output / "ARCHITECTURE_CASE_SUMMARY.csv"
        ),
        results / "RF_CHAIN_PORT_MAPPING.csv": (
            output / "RF_CHAIN_PORT_MAPPING.csv"
        ),
        ROOT
        / "source_inputs/practical_architecture_mapping_v1/"
        "ARCHITECTURE_SOURCE_RECORDS.json": (
            output / "ARCHITECTURE_SOURCE_RECORDS.json"
        ),
        ROOT
        / "source_inputs/practical_architecture_mapping_v1/"
        "SIONNA_8X8_DUAL_PORT_ORDER.csv": (
            output / "SIONNA_8X8_DUAL_PORT_ORDER.csv"
        ),
        ROOT / "docs/PHASE1_CAMPAIGN_REVIEW_PROTOCOL.md": (
            output / "PHASE1_CAMPAIGN_REVIEW_PROTOCOL.md"
        ),
        ROOT / "docs/PRACTICAL_64T64R_ARCHITECTURE_MAPPING.md": (
            output / "PRACTICAL_64T64R_ARCHITECTURE_MAPPING.md"
        ),
    }
    for source, target in copies.items():
        if not source.is_file():
            raise FileNotFoundError(source)
        shutil.copy2(source, target)

    manifest = output / "BUNDLE_MANIFEST.sha256"
    lines = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path != manifest:
            lines.append(
                f"{sha256_file(path)}  {path.relative_to(output).as_posix()}"
            )
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    zip_path = output / "FR3_PHASE1_CAMPAIGN_REVIEW_CANDIDATE_v1.zip"
    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        allowZip64=True,
    ) as archive:
        for path in sorted(output.rglob("*")):
            if path.is_file() and path != zip_path:
                archive.write(path, path.relative_to(output).as_posix())
    with zipfile.ZipFile(zip_path) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError(f"corrupt candidate member: {bad}")
    Path(str(zip_path) + ".sha256").write_text(
        f"{sha256_file(zip_path)}  {zip_path.name}\n",
        encoding="utf-8",
    )

    print("PHASE-1 CAMPAIGN REVIEW CANDIDATE: PASS")
    print("Bundle:", zip_path)
    print("SHA-256:", sha256_file(zip_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
