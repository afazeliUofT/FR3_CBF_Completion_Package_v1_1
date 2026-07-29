#!/usr/bin/env python3
"""Synchronize project status after validating the full-topology export."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- BEGIN VALIDATED FULL-TOPOLOGY EXPORT -->"
END = "<!-- END VALIDATED FULL-TOPOLOGY EXPORT -->"


def replace_block(text: str, block: str) -> str:
    if BEGIN in text and END in text:
        start = text.index(BEGIN)
        stop = text.index(END, start) + len(END)
        return text[:start] + block + text[stop:]
    return block + "\n\n" + text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="config/full_topology_ingest_v4.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    evidence = ROOT / cfg["paths"]["evidence_dir"]
    metrics = json.loads(
        (
            evidence / "FULL_TOPOLOGY_SCIENTIFIC_METRICS.json"
        ).read_text(encoding="utf-8")
    )

    total_min = metrics["common_scale_reference"][
        "total_band_network_retention_quantiles"
    ]["minimum"]
    protected_min = metrics["common_scale_reference"][
        "protected_band_network_retention_quantiles"
    ]["minimum"]
    block = f"""{BEGIN}
## Validated controller-ready full-topology export

- Source H100 job: `18696267`
- Corrected CPU validation job: `18704028`
- Full topology: 228 users, 57 sectors, 128 ports, 9 frequencies
- Full response shape: `[228,57,128,9]`
- V4 validation: `PASS`
- Legacy job-18658301 reproduction: bitwise channel hash match
- Minimum total-band common-scale retention: `{total_min:.6%}`
- Minimum protected-band common-scale retention: `{protected_min:.6%}`
- Claim boundary: `CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_ONE_SEED_NOT_PAPER_RESULT`

The full-versus-chunked network sum differs by only about 0.15%, but the
per-user nominal-rate correlation is only about 0.293. This confirms that the
full topology is necessary for user-level controller evaluation.

The exported pass contains a natural delay/slew safety trap, but no practical
predictive controller has yet been demonstrated.

**Next gate:** `{cfg['next_gate']}`
{END}"""

    project_path = ROOT / "PROJECT_STATUS.md"
    project_text = (
        project_path.read_text(encoding="utf-8")
        if project_path.is_file()
        else "# Current Project Status\n"
    )
    project_path.write_text(
        replace_block(project_text, block),
        encoding="utf-8",
    )

    next_text = f"""# Next Immediate Step

## Gate

`{cfg['next_gate']}`

## Work location

Local WSL. No new Nibi channel generation is needed.

## Required sequence

1. Use the validated full controller dataset under
   `{cfg['paths']['local_data_dir']}`.
2. Implement and test, under the same information, delay, update period and
   slew limit:
   - common-scale oracle reference;
   - static nonuniform allocation;
   - myopic utility-aware safety;
   - virtual-queue baseline;
   - predictive/CBF safety filter.
3. Separate total-band and protected-band utility.
4. Include user-tail and outage metrics, not only network sum rate.
5. Construct the natural rate-limit counterexample around the steep coupling
   rise found in the frozen pass.
6. Do not launch a multi-seed campaign until the predictive method shows a
   safety-utility advantage over fair baselines.
"""
    (ROOT / "NEXT_IMMEDIATE_STEP.md").write_text(
        next_text,
        encoding="utf-8",
    )

    state = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": (
            "PASS_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_ONE_SEED"
        ),
        "source_h100_job_id": "18696267",
        "source_h100_job_state": (
            "FAILED_AFTER_EXPORT_DUE_TO_SUPERSEDED_VALIDATOR"
        ),
        "validation_cpu_job_id": "18704028",
        "validation_cpu_job_state": "COMPLETED",
        "full_return_sha256": cfg["expected"]["full_zip_sha256"],
        "compact_review_sha256": cfg["expected"][
            "review_zip_sha256"
        ],
        "paper_result": False,
        "dynamic_controller_proven": False,
        "next_gate": cfg["next_gate"],
    }
    (ROOT / "config/full_topology_validated_state_v4.json").write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print("FULL-TOPOLOGY STATUS SYNC: PASS")
    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
