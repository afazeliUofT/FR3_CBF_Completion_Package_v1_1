#!/usr/bin/env python3
"""Deterministic randomized audit of the candidate-v4.1 exact formulations.

This is a local release gate, not confirmatory evidence.  It checks:
1. exact equivalence of the floor/SINR linearization and direct rate evaluation;
2. identity of physical-second EESS rows and direct normalized EESS evaluation;
3. the frozen-grid MILP feasibility decision against exhaustive enumeration on
   small randomly generated systems.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
from pathlib import Path

import numpy as np

from fr3_cbf.floor_feasibility_repair import (
    LinearSystem,
    eess_system_for_stream_scales,
    exact_eess_ratio_from_stream_scale,
    exact_rates_from_stream_scale,
    floor_system_for_stream_scales,
    solve_frozen_sector_grid,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=20260801)
    args = parser.parse_args()
    rng = np.random.default_rng(args.seed)

    floor_checks = 0
    for case in range(80):
        users = int(rng.integers(1, 7))
        sectors = int(rng.integers(1, 5))
        streams = int(rng.integers(1, 5))
        gain = 10.0 ** rng.uniform(-3.0, 1.0, size=(users, sectors, streams))
        serving = rng.integers(0, sectors, size=users)
        serving_stream = rng.integers(0, streams, size=users)
        active = rng.random(users) > 0.15
        eligible = rng.random(users) > 0.10
        other = rng.uniform(0.0, 0.25, size=users)
        noise = float(10.0 ** rng.uniform(-3.0, -0.2))
        protected_weight = float(rng.uniform(0.1, 0.9))
        reference_scale = rng.random((sectors, streams))
        reference_rate, _ = exact_rates_from_stream_scale(
            gain,
            reference_scale,
            other,
            active,
            serving,
            serving_stream,
            noise,
            protected_weight,
        )
        floors = np.maximum(
            0.0, reference_rate + rng.uniform(-0.15, 0.15, size=users)
        )
        system = floor_system_for_stream_scales(
            gain,
            other,
            active,
            eligible,
            floors,
            serving,
            serving_stream,
            noise,
            protected_weight,
        )
        for _ in range(30):
            scale = rng.random((sectors, streams))
            rate, _ = exact_rates_from_stream_scale(
                gain,
                scale,
                other,
                active,
                serving,
                serving_stream,
                noise,
                protected_weight,
            )
            linear_feasible = bool(
                np.all(system.a_ub @ scale.reshape(-1) <= system.b_ub + 2e-11)
            )
            valid = active & eligible & (floors > 0.0)
            exact_feasible = bool(np.all(rate[valid] >= floors[valid] - 2e-11))
            if linear_feasible != exact_feasible:
                raise AssertionError(
                    f"floor equivalence failed in case {case}: "
                    f"linear={linear_feasible}, exact={exact_feasible}"
                )
            floor_checks += 1

    eess_rows = 0
    for case in range(100):
        long_seconds = int(rng.integers(1, 8))
        short_seconds = int(rng.integers(1, 8))
        sectors = int(rng.integers(1, 6))
        streams = int(rng.integers(1, 5))
        leakage = rng.uniform(0.0, 2.0, size=(sectors, streams))
        scale = rng.random((sectors, streams))
        long_kappa = rng.uniform(0.0, 3.0, size=(long_seconds, sectors))
        short_kappa = rng.uniform(0.0, 3.0, size=(short_seconds, sectors))
        long_allowance = rng.uniform(0.2, 8.0, size=long_seconds)
        short_allowance = rng.uniform(0.2, 8.0, size=short_seconds)
        uplift_db = float(rng.uniform(0.0, 6.0))
        system = eess_system_for_stream_scales(
            long_kappa,
            short_kappa,
            leakage,
            long_allowance,
            short_allowance,
            uplift_db,
        )
        direct = np.concatenate(
            [
                exact_eess_ratio_from_stream_scale(
                    long_kappa, leakage, scale, long_allowance, uplift_db
                ),
                exact_eess_ratio_from_stream_scale(
                    short_kappa, leakage, scale, short_allowance, uplift_db
                ),
            ]
        )
        reconstructed = system.a_ub @ scale.reshape(-1)
        if not np.allclose(reconstructed, direct, rtol=2e-15, atol=2e-13):
            raise AssertionError(f"EESS row identity failed in case {case}")
        eess_rows += len(direct)

    grid_db = [0.0, 3.0, 6.0, math.inf]
    grid_scale = np.asarray([1.0, 10.0 ** -0.3, 10.0 ** -0.6, 0.0])
    exhaustive_cases = 0
    for case in range(60):
        sectors = int(rng.integers(1, 5))
        rows = int(rng.integers(1, 8))
        matrix = rng.uniform(-2.0, 2.0, size=(rows, sectors))
        known_witness = grid_scale[
            rng.integers(0, len(grid_scale), size=sectors)
        ]
        if case % 2 == 0:
            bound = matrix @ known_witness + rng.uniform(0.0, 0.2, size=rows)
        else:
            bound = rng.uniform(-1.0, 1.0, size=rows)
        system = LinearSystem(
            matrix,
            bound,
            tuple(f"random-row-{row}" for row in range(rows)),
        )
        baseline = grid_scale[
            rng.integers(0, len(grid_scale), size=sectors)
        ]
        outcome = solve_frozen_sector_grid(
            system, baseline, grid_db, time_limit_s=10.0
        )
        brute_force_feasible = False
        for values in itertools.product(grid_scale, repeat=sectors):
            decision = np.asarray(values)
            if np.all(matrix @ decision <= bound + 1e-10):
                brute_force_feasible = True
                break
        if outcome.feasible != brute_force_feasible:
            raise AssertionError(
                f"MILP/exhaustive mismatch in case {case}: "
                f"solver={outcome.status}, brute={brute_force_feasible}"
            )
        if outcome.feasible and (
            outcome.decision is None
            or not np.all(matrix @ outcome.decision <= bound + 5e-9)
        ):
            raise AssertionError(f"MILP returned an invalid witness in case {case}")
        exhaustive_cases += 1

    report = {
        "schema_version": 1,
        "status": "PASS_DETERMINISTIC_RANDOMIZED_MODEL_AUDIT",
        "seed": args.seed,
        "floor_linearization_direct_equivalence_checks": floor_checks,
        "physical_second_eess_row_identity_checks": eess_rows,
        "frozen_grid_milp_vs_exhaustive_cases": exhaustive_cases,
        "scope": "local mathematical/model regression; not seed or campaign evidence",
        "confirmatory_campaign_authorized": False,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"RANDOM_FLOOR_LINEARIZATION_CHECKS={floor_checks}")
    print("RANDOM_FLOOR_LINEARIZATION=PASS")
    print(f"RANDOM_EESS_ROW_CHECKS={eess_rows}")
    print("RANDOM_EESS_LINEARIZATION=PASS")
    print(f"SMALL_MILP_EXHAUSTIVE_CASES={exhaustive_cases}")
    print("FROZEN_GRID_MILP_VS_EXHAUSTIVE=PASS")
    print("RANDOMIZED_MODEL_AUDIT=PASS")
    print("CONFIRMATORY_CAMPAIGN_AUTHORIZED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
