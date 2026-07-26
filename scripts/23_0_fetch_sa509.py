#!/usr/bin/env python3
"""Archive the official ITU-R SA.509-3 PDF with fail-closed validation."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_URL = (
    "https://www.itu.int/dms_pubrec/itu-r/rec/sa/"
    "R-REC-SA.509-3-201312-I%21%21PDF-E.pdf"
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_pdf_bytes(data: bytes) -> None:
    if len(data) < 100_000:
        raise ValueError(f"Downloaded SA.509 object is too small for the official PDF: {len(data)} bytes")
    if not data.startswith(b"%PDF-"):
        preview = data[:120].decode("utf-8", errors="replace")
        raise ValueError(f"Downloaded SA.509 object is not a PDF; preview={preview!r}")
    if b"%%EOF" not in data[-4096:]:
        raise ValueError("Downloaded SA.509 PDF has no EOF marker near the end")


def fetch(url: str, retries: int = 5, timeout_s: int = 120) -> tuple[bytes, dict[str, str]]:
    errors: list[str] = []
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "FR3-CBF-SA509-archive/1.0 academic reproducibility"},
            )
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                data = response.read()
                headers = {str(k): str(v) for k, v in response.headers.items()}
            validate_pdf_bytes(data)
            return data, headers
        except Exception as exc:  # preserve all errors for the final diagnosis
            errors.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
            if attempt < retries:
                time.sleep(min(2 ** (attempt - 1), 8))
    raise RuntimeError("Could not retrieve official SA.509-3 PDF:\n" + "\n".join(errors))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", default="data/external/itu/R-REC-SA.509-3-201312-I!!PDF-E.pdf")
    parser.add_argument("--record", default="data/external/itu/SA509_SOURCE_RECORD.json")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    output = root / args.output
    record_path = root / args.record
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not args.force:
        data = output.read_bytes()
        validate_pdf_bytes(data)
        mode = "existing_validated_copy"
        headers: dict[str, str] = {}
    else:
        data, headers = fetch(args.url)
        output.write_bytes(data)
        mode = "official_url_download"
    record = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "recommendation": "ITU-R SA.509-3",
        "recommendation_status": "IN_FORCE_AT_WORKFLOW_DESIGN_TIME_VERIFY_BEFORE_SUBMISSION",
        "official_url": args.url,
        "retrieval_mode": mode,
        "pdf_path": str(output.relative_to(root)),
        "pdf_size_bytes": len(data),
        "pdf_sha256": sha256_bytes(data),
        "response_headers": headers,
        "use_boundary": (
            "Reference large-parabolic-antenna pattern used because measured station pattern is unavailable; "
            "this workflow does not claim SA.509 is an EESS-specific mandatory pattern."
        ),
    }
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("SA.509 SOURCE ARCHIVE: PASS")
    print(f"PDF: {output}")
    print(f"Bytes: {len(data)}")
    print(f"SHA-256: {record['pdf_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
