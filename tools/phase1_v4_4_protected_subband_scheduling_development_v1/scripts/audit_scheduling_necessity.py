#!/usr/bin/env python3
"""Quantify why protected-resource scheduling is the next justified action."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import zipfile

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnosis-zip", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()

    rows = []
    with zipfile.ZipFile(args.diagnosis_zip) as zf:
        if zf.testzip() is not None:
            raise RuntimeError("diagnosis ZIP CRC failure")
        root = zf.namelist()[0].split("/", 1)[0]
        for name in zf.namelist():
            if name.endswith("/AFFECTED_USER_DIAGNOSIS.csv"):
                with tempfile.NamedTemporaryFile(suffix=".csv") as handle:
                    handle.write(zf.read(name)); handle.flush()
                    rows.append(pd.read_csv(handle.name))
    frame = pd.concat(rows, ignore_index=True)
    if len(frame) != 4016:
        raise RuntimeError(f"affected-user row count mismatch: {len(frame)}")
    if not bool(frame["optimistic_single_user_floor_feasible"].all()):
        raise RuntimeError("at least one affected user is individually infeasible")

    # Infer the unchanged non-protected-band contribution from the diagnostic
    # contract (protected weight = 0.1).  Then compute the dedicated protected-
    # resource fraction needed under the optimistic single-user column while
    # conservatively assigning zero protected contribution outside that user's
    # dedicated fraction.  This is a plausibility bound, not an exact schedule.
    protected_weight = 0.1
    other_rate = (
        frame["optimistic_total_rate_bps_hz"]
        - protected_weight * frame["optimistic_protected_rate_bps_hz"]
    )
    required = (
        frame["floor_bps_hz"] - other_rate
    ) / (
        protected_weight * frame["optimistic_protected_rate_bps_hz"]
    )
    frame["conservative_required_fraction"] = required.clip(lower=0.0)
    interval = frame.groupby(["campaign_seed", "pass_slot", "interval_index"], as_index=False)[
        "conservative_required_fraction"
    ].sum()
    sector = frame.groupby(
        ["campaign_seed", "pass_slot", "interval_index", "serving_sector"], as_index=False
    )["conservative_required_fraction"].sum()
    record = {
        "schema_version": 1,
        "status": "PASS_SCHEDULING_NECESSITY_AND_PLAUSIBILITY_AUDIT",
        "affected_user_rows": int(len(frame)),
        "affected_intervals": int(len(interval)),
        "all_affected_users_individually_serviceable": True,
        "maximum_conservative_single_user_dedicated_fraction": float(
            frame["conservative_required_fraction"].max()
        ),
        "maximum_conservative_global_dedicated_fraction_sum": float(
            interval["conservative_required_fraction"].max()
        ),
        "maximum_conservative_per_sector_dedicated_fraction_sum": float(
            sector["conservative_required_fraction"].max()
        ),
        "intervals_exceeding_unit_resource_under_conservative_bound": int(
            (interval["conservative_required_fraction"] > 1.0).sum()
        ),
        "scientific_interpretation": (
            "fixed-beam simultaneous service is frequently jointly infeasible, "
            "but every affected user is individually serviceable and the summed "
            "optimistic isolated protected-resource demand remains below one in "
            "every diagnosed interval; this does not prove a feasible guarded "
            "schedule, but it supports protected-resource scheduling as the "
            "minimal scientifically justified next degree of freedom"
        ),
        "claim_boundary": (
            "DIAGNOSIS_DERIVED_PLAUSIBILITY_BOUND_NOT_AN_EXACT_V4_4_CHANNEL_RESULT"
        ),
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print("SCHEDULING_NECESSITY_AND_PLAUSIBILITY_AUDIT=PASS")
    print(f"AFFECTED_INTERVAL_COUNT={len(interval)}")
    print(
        "MAXIMUM_CONSERVATIVE_SINGLE_USER_DEDICATED_FRACTION="
        f"{record['maximum_conservative_single_user_dedicated_fraction']:.17g}"
    )
    print(
        "MAXIMUM_CONSERVATIVE_GLOBAL_DEDICATED_FRACTION_SUM="
        f"{record['maximum_conservative_global_dedicated_fraction_sum']:.17g}"
    )
    print(
        "MAXIMUM_CONSERVATIVE_PER_SECTOR_DEDICATED_FRACTION_SUM="
        f"{record['maximum_conservative_per_sector_dedicated_fraction_sum']:.17g}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
