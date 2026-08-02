#!/usr/bin/env python3
"""Verify complete or partial v4.4 scheduling development returns."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

EXPECTED_SEEDS = [44001, 44007, 44008, 44013, 44017, 44018, 44024, 44025, 44026, 44027, 44028]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--return-zip", type=Path, required=True)
    p.add_argument("--expected-sha256", required=True)
    p.add_argument("--output-json", type=Path, required=True)
    a = p.parse_args()
    archive = a.return_zip.resolve()
    digest = sha256_file(archive)
    if digest != a.expected_sha256:
        raise RuntimeError(f"return SHA mismatch: {digest}")
    with zipfile.ZipFile(archive) as zf:
        bad = zf.testzip()
        if bad is not None:
            raise RuntimeError(f"return ZIP CRC failure: {bad}")
        roots = sorted({n.split("/", 1)[0] for n in zf.namelist() if "/" in n})
        if len(roots) != 1:
            raise RuntimeError("return ZIP must have one root")
        root = roots[0]
        with tempfile.TemporaryDirectory() as temp:
            zf.extractall(temp)
            extracted = Path(temp) / root
            manifest = extracted / "RETURN_MANIFEST.sha256"
            if not manifest.is_file():
                raise RuntimeError("return manifest missing")
            for line in manifest.read_text(encoding="utf-8").splitlines():
                expected, relative = line.split(maxsplit=1)
                relative = relative.strip()
                path = extracted / relative
                if not path.is_file() or sha256_file(path) != expected:
                    raise RuntimeError(f"return manifest mismatch: {relative}")
            metadata_path = extracted / "RETURN_METADATA.json"
            emergency_path = extracted / "EMERGENCY_RETURN_STATUS.json"
            if metadata_path.is_file():
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                emergency_return = False
            elif emergency_path.is_file():
                metadata = json.loads(emergency_path.read_text(encoding="utf-8"))
                emergency_return = True
            else:
                raise RuntimeError("return metadata/status missing")
            summary_path = extracted / "merged/V44_SCHEDULING_DEVELOPMENT_SUMMARY.json"
            summary = (
                json.loads(summary_path.read_text())
                if summary_path.is_file()
                else {
                    "status": metadata.get("status", "NO_MERGED_SUMMARY"),
                    "next_repair_decision": None,
                    "next_gate": metadata.get("next_gate", "REVIEW_INFRASTRUCTURE"),
                }
            )
            seed_root = extracted / ("tasks" if emergency_return else "seed_results")
            present = sorted(
                int(path.name.split("_", 1)[1])
                for path in seed_root.glob("seed_*")
                if (path / "result/V44_SCHEDULING_SEED_RESULT.json").is_file()
            ) if seed_root.is_dir() else []
            merged_summary_present = summary_path.is_file()
    missing = sorted(set(EXPECTED_SEEDS) - set(present))
    complete = (
        not emergency_return
        and present == EXPECTED_SEEDS
        and merged_summary_present
    )
    record = {
        "schema_version": 1,
        "status": (
            "PASS_COMPLETE_V44_SCHEDULING_DEVELOPMENT_RETURN"
            if complete
            else "PASS_VALID_PARTIAL_V44_SCHEDULING_DEVELOPMENT_RETURN"
        ),
        "return_zip_sha256": digest,
        "return_zip_crc": "PASS",
        "return_manifest": "PASS",
        "failed_seed_return_count": len(present),
        "missing_failed_seeds": missing,
        "return_completeness": "COMPLETE" if complete else "PARTIAL",
        "v44_scheduling_development_status": summary.get("status"),
        "next_repair_decision": summary.get("next_repair_decision"),
        "next_gate": summary.get("next_gate"),
        "scientific_pass": complete and str(summary.get("status", "")).startswith("PASS_"),
        "fresh_confirmation": False,
        "campaign_rerun_authorized": False,
        "metadata_status": metadata.get("status"),
        "emergency_return": bool(emergency_return),
    }
    a.output_json.parent.mkdir(parents=True, exist_ok=True)
    a.output_json.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print("V44_SCHEDULING_RETURN_SHA256_GATE=PASS")
    print("V44_SCHEDULING_RETURN_ZIP_CRC=PASS")
    print("V44_SCHEDULING_RETURN_MANIFEST=PASS")
    print(f"V44_SCHEDULING_RETURN_COMPLETENESS={record['return_completeness']}")
    print(f"FAILED_SEED_RETURN_COUNT={len(present)}")
    print("MISSING_FAILED_SEEDS=" + ",".join(str(v) for v in missing))
    print(f"V44_SCHEDULING_DEVELOPMENT_STATUS={summary.get('status')}")
    print(f"NEXT_REPAIR_DECISION={summary.get('next_repair_decision')}")
    print(f"NEXT_GATE={summary.get('next_gate')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
