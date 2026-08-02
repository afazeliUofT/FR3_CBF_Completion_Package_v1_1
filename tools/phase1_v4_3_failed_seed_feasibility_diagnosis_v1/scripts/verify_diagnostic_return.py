#!/usr/bin/env python3
"""Verify a failed-seed diagnostic return without hiding partial failures."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ALLOWED_DECISIONS = {
    "ADAPTIVE_LOCAL_FIXED_BEAM_REPAIR",
    "PROTECTED_SUBBAND_SCHEDULING_REASSIGNMENT_REQUIRED",
    "SOLVER_CERTIFICATE_REFINEMENT_REQUIRED",
    "NUMERICAL_INTERIOR_WITNESS_REFINEMENT_REQUIRED",
    "BROADER_COORDINATION_OR_SCHEDULING_REQUIRED",
}
EXPECTED_SEEDS = {
    44001,
    44007,
    44008,
    44013,
    44017,
    44018,
    44024,
    44025,
    44026,
    44027,
    44028,
}


def sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--return-zip", type=Path, required=True)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()

    path = args.return_zip.resolve()
    digest = sha256_file(path)
    if args.expected_sha256 and digest != args.expected_sha256:
        raise RuntimeError(
            f"return SHA mismatch: {digest} != {args.expected_sha256}"
        )

    with zipfile.ZipFile(path) as zf:
        bad = zf.testzip()
        if bad is not None:
            raise RuntimeError(f"ZIP CRC failure: {bad}")
        roots = sorted({name.split("/", 1)[0] for name in zf.namelist() if "/" in name})
        if len(roots) != 1:
            raise RuntimeError(f"expected one return root, found {roots}")
        prefix = roots[0] + "/"
        manifest_name = prefix + "RETURN_MANIFEST.sha256"
        if manifest_name not in zf.namelist():
            raise RuntimeError("return manifest missing")
        manifest_count = 0
        for line in zf.read(manifest_name).decode("utf-8").splitlines():
            if not line.strip():
                continue
            expected, rel = line.split(maxsplit=1)
            actual = hashlib.sha256(zf.read(prefix + rel)).hexdigest()
            if actual != expected:
                raise RuntimeError(f"manifest mismatch: {rel}")
            manifest_count += 1

        status = json.loads(zf.read(prefix + "RETURN_STATUS.json").decode("utf-8"))
        seed_ids = set()
        for name in zf.namelist():
            marker = prefix + "seed_diagnostics/seed_"
            if not name.startswith(marker):
                continue
            remainder = name[len(marker):]
            token = remainder.split("/", 1)[0]
            if token.isdigit():
                seed_ids.add(int(token))

        decision_path = prefix + "merged/NEXT_REPAIR_DECISION.json"
        complete = decision_path in zf.namelist()
        decision = None
        next_gate = None
        diagnosed_intervals = None
        if complete:
            record = json.loads(zf.read(decision_path).decode("utf-8"))
            decision = record["next_repair_decision"]
            next_gate = record["next_gate"]
            diagnosed_intervals = int(record["diagnosed_unresolved_interval_count"])
            if decision not in ALLOWED_DECISIONS:
                raise RuntimeError(f"unknown scientific decision: {decision}")
            if seed_ids != EXPECTED_SEEDS:
                raise RuntimeError(
                    f"complete return has wrong seed set: {sorted(seed_ids)}"
                )
            if diagnosed_intervals != 1736:
                raise RuntimeError(
                    f"diagnosed interval count mismatch: {diagnosed_intervals}"
                )

    summary = {
        "schema_version": 1,
        "status": (
            "PASS_COMPLETE_DIAGNOSTIC_RETURN_VERIFICATION"
            if complete
            else "PASS_PARTIAL_DIAGNOSTIC_RETURN_VERIFICATION_REVIEW_REQUIRED"
        ),
        "return_zip_sha256": digest,
        "return_manifest_entries": manifest_count,
        "seed_return_count": len(seed_ids),
        "seed_ids": sorted(seed_ids),
        "complete_scientific_decision_available": complete,
        "next_repair_decision": decision,
        "next_gate": next_gate,
        "diagnosed_unresolved_interval_count": diagnosed_intervals,
        "return_status": status,
    }
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    print("DIAGNOSTIC_RETURN_SHA256_GATE=PASS")
    print("DIAGNOSTIC_RETURN_ZIP_CRC=PASS")
    print("DIAGNOSTIC_RETURN_MANIFEST=PASS")
    print(f"DIAGNOSTIC_RETURN_MANIFEST_ENTRIES={manifest_count}")
    print(f"DIAGNOSTIC_SEED_RETURN_COUNT={len(seed_ids)}")
    print(
        "DIAGNOSTIC_RETURN_COMPLETENESS="
        + ("COMPLETE" if complete else "PARTIAL_REVIEW_REQUIRED")
    )
    if complete:
        print(f"NEXT_REPAIR_DECISION={decision}")
        print(f"NEXT_GATE={next_gate}")
        return 0
    print("NEXT_REPAIR_DECISION=UNAVAILABLE_DIAGNOSTIC_RETURN_REVIEW_REQUIRED")
    print("NEXT_GATE=REVIEW_FAILED_SEED_DIAGNOSTIC_INFRASTRUCTURE")
    return 42


if __name__ == "__main__":
    raise SystemExit(main())
