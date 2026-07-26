from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from _bootstrap import ROOT
from fr3_cbf.beam_filter import solve_minimal_deviation_filter
from fr3_cbf.bundle import validate_bundle
from fr3_cbf.io import write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the optional fully digital finite-scenario CVXPY benchmark")
    parser.add_argument("--bundle", default="data/demo/experiment_bundle_template.npz")
    parser.add_argument("--output", default="results/beam_space_filter")
    parser.add_argument("--solver")
    parser.add_argument("--slack-penalty", type=float, default=1e8)
    args = parser.parse_args()
    path = Path(args.bundle)
    validate_bundle(path)
    with np.load(path, allow_pickle=False) as z:
        w = z["nominal_beamformers"]
        r = z["coupling"]
        thresholds = np.asarray(z["thresholds"], dtype=float)
        tone_weights = np.asarray(z["tone_weights"], dtype=float)
    if w.ndim != 4 or r.ndim != 5:
        raise SystemExit("This reference script expects a static bundle")
    coupling_scenarios = r[:, None, ...]
    previous = w.copy()
    power = np.array([1.10 * sum(tone_weights[t] * np.linalg.norm(w[b, t]) ** 2 for t in range(w.shape[1])) for b in range(w.shape[0])])
    slew = np.full(w.shape[0], 10.0)
    result = solve_minimal_deviation_filter(
        w, previous, coupling_scenarios, thresholds, tone_weights, power, slew,
        slack_penalty=args.slack_penalty, solver=args.solver,
    )
    out = ROOT / args.output
    out.mkdir(parents=True, exist_ok=True)
    if result.beamformers is not None:
        np.savez_compressed(out / "safe_beamformers.npz", safe_beamformers=result.beamformers, slack=result.slack)
    write_json(
        out / "audit.json",
        {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "bundle": str(path),
            "status": result.status,
            "objective_value": result.objective_value,
            "solve_time_s": result.solve_time_s,
            "solver": result.solver_name,
            "slack": None if result.slack is None else result.slack.tolist(),
            "claim_boundary": "Small-network fully digital benchmark; not a production near-real-time result.",
        },
    )
    print(f"BEAM FILTER: status={result.status}, solve_time_s={result.solve_time_s:.6f}")
    return 0 if result.beamformers is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
