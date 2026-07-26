#!/usr/bin/env python3
"""Fetch once, validate, and archive the E3 geometry reference TLE."""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

USER_AGENT = "FR3-CBF-E3-reference/1.0 academic reproducibility workflow"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def checksum_ok(line: str) -> bool:
    if len(line) < 69 or not line[68].isdigit():
        return False
    total = 0
    for char in line[:68]:
        if char.isdigit():
            total += int(char)
        elif char == "-":
            total += 1
    return total % 10 == int(line[68])


def tle_epoch(line1: str) -> datetime:
    raw = line1[18:32]
    year2 = int(raw[:2])
    year = 1900 + year2 if year2 >= 57 else 2000 + year2
    day = float(raw[2:])
    return datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=day - 1.0)


def parse_tle(text: str, expected_cat: int) -> tuple[str, str, str, datetime]:
    lines = [line.rstrip("\r\n") for line in text.splitlines() if line.strip()]
    if len(lines) == 2:
        name, line1, line2 = f"NORAD {expected_cat}", lines[0], lines[1]
    elif len(lines) == 3:
        name, line1, line2 = lines
    else:
        raise ValueError(f"Expected 2 or 3 nonblank TLE lines; found {len(lines)}")
    if not (line1.startswith("1 ") and line2.startswith("2 ")):
        raise ValueError("Downloaded payload is not a TLE")
    if int(line1[2:7]) != expected_cat or int(line2[2:7]) != expected_cat:
        raise ValueError("TLE catalog number does not match the requested object")
    if not checksum_ok(line1) or not checksum_ok(line2):
        raise ValueError("TLE checksum validation failed")
    return name.strip(), line1[:69], line2[:69], tle_epoch(line1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/e3_reference_intake.yaml")
    parser.add_argument("--input-file", help="Validate an already downloaded TLE instead of using the network")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    cfg = yaml.safe_load((root / args.config).read_text(encoding="utf-8"))
    mission = cfg["mission"]
    expected_cat = int(mission["norad_catalog_number"])
    out_dir = root / "data/external/tle"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "active_case.tle"
    headers_out = out_dir / "active_case_response_headers.txt"
    retrieval_utc = datetime.now(timezone.utc)
    source_mode = "existing"
    headers_text = ""
    if args.input_file:
        source = Path(args.input_file).expanduser().resolve()
        text = source.read_text(encoding="utf-8")
        source_mode = f"input_file:{source}"
    elif out.is_file() and not args.force:
        text = out.read_text(encoding="utf-8")
    else:
        request = urllib.request.Request(
            mission["celestrak_tle_url"],
            headers={"User-Agent": USER_AGENT},
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = response.read()
            headers_text = str(response.headers)
        text = payload.decode("utf-8")
        source_mode = "celestrak_single_query"
    name, line1, line2, epoch = parse_tle(text, expected_cat)
    age_days = (retrieval_utc - epoch).total_seconds() / 86400.0
    max_age = float(mission["maximum_tle_age_days"])
    if age_days < -1.0:
        raise ValueError(f"TLE epoch is implausibly in the future: age={age_days:.3f} d")
    if age_days > max_age:
        raise ValueError(f"TLE is too old: age={age_days:.3f} d > {max_age:.3f} d")
    out.write_text(f"{name}\n{line1}\n{line2}\n", encoding="utf-8", newline="\n")
    if headers_text:
        headers_out.write_text(headers_text, encoding="utf-8")
    record = {
        "retrieved_utc": retrieval_utc.isoformat(),
        "source_mode": source_mode,
        "source_url": mission["celestrak_tle_url"],
        "provider": "CelesTrak",
        "name_line": name,
        "norad_catalog_number": expected_cat,
        "tle_epoch_utc": epoch.isoformat(),
        "tle_age_days_at_validation": age_days,
        "maximum_tle_age_days": max_age,
        "tle_sha256": sha256_file(out),
        "geometry_only_claim": mission["geometry_only_claim"],
        "usage_note": "Archive and reuse this file; do not repeatedly query CelesTrak within one update interval.",
    }
    (out_dir / "TLE_SOURCE_RECORD.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("E3 TLE FETCH/VALIDATION: PASS")
    print(f"Name: {name}")
    print(f"NORAD catalog: {expected_cat}")
    print(f"TLE epoch: {epoch.isoformat()}")
    print(f"TLE age: {age_days:.3f} days")
    print(f"Output: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
