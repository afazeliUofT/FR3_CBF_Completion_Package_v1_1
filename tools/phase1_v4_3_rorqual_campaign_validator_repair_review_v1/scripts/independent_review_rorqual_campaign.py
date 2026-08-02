#!/usr/bin/env python3
"""Independent review of the corrected Rorqual-native locked campaign package."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

import pandas as pd

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def deterministic_review_zip(root: Path, output: Path) -> None:
    fixed = (2026, 8, 2, 0, 0, 0)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.iterdir()):
            if not path.is_file() or path == output or path == Path(str(output) + ".sha256"):
                continue
            info = zipfile.ZipInfo(path.name, fixed)
            info.external_attr = (path.stat().st_mode & 0xFFFF) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    with zipfile.ZipFile(output) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError(f"review ZIP CRC failure: {bad}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-root", required=True)
    parser.add_argument("--build-root", required=True)
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()
    audit_root = Path(args.audit_root).expanduser().resolve()
    build_root = Path(args.build_root).expanduser().resolve()
    output = Path(args.output_root).expanduser().resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    config = json.loads(
        (PACKAGE_ROOT / "config/REPAIR_REVIEW_CONTRACT.json").read_text(
            encoding="utf-8"
        )
    )
    verdict = json.loads(
        (audit_root / "SMOKE_RECLASSIFICATION_VERDICT.json").read_text()
    )
    if verdict["scientific_result"] != "PASS":
        raise ValueError("excluded smoke has not been reclassified PASS")
    build_audit = json.loads((build_root / "BUILD_AUDIT.json").read_text())
    package_zip = build_root / config["new_locked_campaign"]["package_filename"]
    sidecar = Path(str(package_zip) + ".sha256")
    parts = sidecar.read_text(encoding="utf-8").split()
    if len(parts) != 2 or parts[1] != package_zip.name:
        raise ValueError("Rorqual job sidecar is not basename-only")
    if parts[0] != sha256_file(package_zip):
        raise ValueError("Rorqual job package SHA-256 mismatch")
    with zipfile.ZipFile(package_zip) as archive:
        if archive.testzip() is not None:
            raise ValueError("Rorqual job package CRC failure")

    checks: dict[str, object] = {}
    with tempfile.TemporaryDirectory(prefix="fr3-v43-rorqual-review-") as temp_name:
        root = Path(temp_name) / "job"
        with zipfile.ZipFile(package_zip) as archive:
            archive.extractall(root)
        subprocess.run(
            ["sha256sum", "-c", "PACKAGE_MANIFEST.sha256"],
            cwd=root,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        contract = json.loads((root / "JOB_PACKAGE_CONTRACT.json").read_text())
        campaign = json.loads(
            (root / "PHASE1_CAMPAIGN_CONTRACT_V4_3.json").read_text()
        )
        schema = json.loads((root / "RESULT_SCHEMA.json").read_text())
        token = json.loads((root / "AUTHORIZATION_TOKEN_TEMPLATE.json").read_text())
        checks.update(
            {
                "package_manifest": "PASS",
                "package_id": contract["package_id"] == build_audit["package_id"],
                "execution_cluster_rorqual": contract["execution_cluster"]
                == "rorqual",
                "rorqual_resource_template": contract[
                    "rorqual_resource_template"
                ]["cluster"]
                == "rorqual",
                "seed_list_exact": contract["campaign_seed_list"]
                == list(range(44000, 44030)),
                "five_passes": int(contract["fixed_pass_count"]) == 5,
                "nine_methods": int(contract["method_count"]) == 9,
                "total_cells": int(contract["total_cells"]) == 1350,
                "candidate_source_unchanged": contract["candidate_v4_3"][
                    "source_manifest_sha256"
                ]
                == "a2e67130c91577b83be6e14f400d0934aa6d94ac0f974956594df35eec0cb93c",
                "candidate_only_na_semantics": schema[
                    "cell_summary_numeric_domain_contract"
                ]["candidate_only_nan_is_not_data_corruption"],
                "geometric_mean_definition_explicit": (
                    "exp(mean(log(x+0.001)))-0.001"
                    in json.dumps(schema["descriptive_metric_definitions"])
                ),
                "execution_locked": not bool(contract["execution_authorized"]),
                "submission_scripts_locked": bool(contract["submission_scripts_locked"]),
                "token_not_included": not bool(
                    contract["authorization_contract"]["token_included"]
                )
                and not bool(token["execution_authorized"])
                and not bool(token["token_included"]),
                "next_gate_separate_authorization": contract["next_gate"]
                == "SEPARATE_RORQUAL_30_SEED_CAMPAIGN_AUTHORIZATION_AND_EXECUTION",
                "information_exchange_not_overclaimed": not bool(
                    contract["information_exchange_locality_certified"]
                ),
                "campaign_contract_not_paper_result": not bool(
                    campaign["paper_result"]
                ),
            }
        )
        if not all(value == "PASS" or value is True for value in checks.values()):
            raise ValueError(f"Rorqual package review failed: {checks}")

        # Re-run the corrected validator on the exact returned excluded smoke.
        smoke_zip = (
            PACKAGE_ROOT
            / "immutable_bindings"
            / config["smoke_return"]["filename"]
        )
        smoke_root = Path(temp_name) / "smoke"
        with zipfile.ZipFile(smoke_zip) as archive:
            archive.extractall(smoke_root)
        roots = [p for p in smoke_root.iterdir() if p.is_dir()]
        if len(roots) != 1:
            raise ValueError("unexpected smoke root")
        result = roots[0] / "result"
        # Use the legacy contract because the returned result is hash-bound to it;
        # only the corrected validator implementation is under review here.
        legacy_zip = (
            PACKAGE_ROOT
            / "immutable_bindings/locked_campaign"
            / config["legacy_locked_campaign"]["filename"]
        )
        legacy_root = Path(temp_name) / "legacy"
        with zipfile.ZipFile(legacy_zip) as archive:
            archive.extractall(legacy_root)
        for require_pass in (False, True):
            command = [
                "python3",
                str(root / "validate_seed_result.py"),
                "--result-dir",
                str(result),
                "--package-contract",
                str(legacy_root / "JOB_PACKAGE_CONTRACT.json"),
            ]
            if require_pass:
                command.append("--require-scientific-pass")
            completed = subprocess.run(command, capture_output=True, text=True)
            if completed.returncode != 0:
                raise RuntimeError(completed.stdout + completed.stderr)
        checks["exact_smoke_corrected_structural_validator"] = "PASS"
        checks["exact_smoke_corrected_scientific_validator"] = "PASS"

        # The corrected merged validator's numeric-domain helper must accept a
        # 30-seed concatenation with comparator candidate-only NaNs.
        cells = pd.read_csv(result / "CELL_SUMMARY.csv")
        merged_cells = pd.concat(
            [cells.assign(campaign_seed=seed) for seed in range(44000, 44030)],
            ignore_index=True,
        )
        import sys
        sys.path.insert(0, str(root))
        from validator_contract import validate_cell_summary_numeric_domains
        domain = validate_cell_summary_numeric_domains(merged_cells)
        if int(domain["row_count"]) != 1350 or int(domain["candidate_row_count"]) != 150:
            raise ValueError(f"merged numeric-domain audit mismatch: {domain}")
        checks["synthetic_30_seed_merged_numeric_domain"] = "PASS"

        # No active script may point execution to Nibi. Historical substrate
        # filenames are allowed only as immutable provenance.
        active_text = "\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in [
                root / "JOB_PACKAGE_CONTRACT.json",
                root / "PHASE1_CAMPAIGN_CONTRACT_V4_3.json",
                root / "README_JOB_PACKAGE.md",
                root / "RUN_PHASE1_RORQUAL_CAMPAIGN.sh",
            ]
        ).lower()
        if "cluster\": \"nibi" in active_text or "run_phase1_nibi_campaign" in active_text:
            raise ValueError("active Rorqual package retains Nibi execution routing")
        checks["active_execution_routing_rorqual_only"] = "PASS"

    review_verdict = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_CORRECTED_RORQUAL_NATIVE_LOCKED_30_SEED_CAMPAIGN_PACKAGE_FOR_SEPARATE_AUTHORIZATION_NOT_EXECUTION",
        "package_id": build_audit["package_id"],
        "package_zip_sha256": sha256_file(package_zip),
        "candidate_source_changed": False,
        "validator_contract_repair": True,
        "excluded_smoke_reclassification": verdict["status"],
        "checks": checks,
        "campaign_execution_authorized": False,
        "cluster_contacted": False,
        "paper_result": False,
        "next_gate": "SEPARATE_RORQUAL_30_SEED_CAMPAIGN_AUTHORIZATION_AND_EXECUTION",
        "claim_boundary": "PACKAGE_REVIEW_NOT_CAMPAIGN_EXECUTION_NOT_PAPER_RESULT",
    }
    write_json(output / "INDEPENDENT_REVIEW_VERDICT.json", review_verdict)
    write_json(output / "REVIEW_CHECK_SUMMARY.json", checks)
    shutil.copy2(audit_root / "SMOKE_RECLASSIFICATION_VERDICT.json", output)
    shutil.copy2(audit_root / "GEOMETRIC_MEAN_DEFINITION_AUDIT.csv", output)
    shutil.copy2(build_root / "BUILD_AUDIT.json", output)
    review_zip = output / config["new_locked_campaign"]["review_filename"]
    deterministic_review_zip(output, review_zip)
    review_sha = sha256_file(review_zip)
    Path(str(review_zip) + ".sha256").write_text(
        f"{review_sha}  {review_zip.name}\n", encoding="utf-8"
    )
    print("RORQUAL_R2_LOCKED_CAMPAIGN_INDEPENDENT_REVIEW=PASS")
    print(
        "INDEPENDENT_REVIEW_VERDICT="
        "PASS_CORRECTED_RORQUAL_NATIVE_LOCKED_30_SEED_CAMPAIGN_PACKAGE_"
        "FOR_SEPARATE_AUTHORIZATION_NOT_EXECUTION"
    )
    print(f"RORQUAL_R2_REVIEW_ZIP={review_zip}")
    print(f"RORQUAL_R2_REVIEW_ZIP_SHA256={review_sha}")
    print("CAMPAIGN_EXECUTION_AUTHORIZED=NO")
    print("CLUSTER_CONTACTED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
