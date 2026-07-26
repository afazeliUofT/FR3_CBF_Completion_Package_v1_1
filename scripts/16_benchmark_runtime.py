from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from _bootstrap import ROOT
from fr3_cbf.io import write_json
from fr3_cbf.safety import cbf_scale


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark the layered scalar-budget safety update")
    parser.add_argument("--mode", choices=["demo", "real"], default="demo")
    parser.add_argument("--repetitions", type=int, default=200)
    args = parser.parse_args()
    sizes = [(19 * 3, 20), (100, 50), (300, 100), (1000, 200)]
    rng = np.random.default_rng(1616)
    rows = []
    for sectors, incumbents in sizes:
        coupling = rng.uniform(0.0, 0.05, size=(incumbents, sectors))
        q = np.ones(sectors)
        start = time.perf_counter()
        for _ in range(args.repetitions):
            aggregate = coupling @ q
            active = aggregate > 0.7
            if np.any(active):
                worst = float(np.max(aggregate[active]))
                target = cbf_scale(1.0, float(np.mean(q)), worst, 1.0, 0.05, 0.1)
                q[:] = target
            else:
                q[:] = np.minimum(1.0, q + 0.05)
        elapsed = time.perf_counter() - start
        rows.append(
            {
                "mode": args.mode,
                "sectors": sectors,
                "incumbents": incumbents,
                "repetitions": args.repetitions,
                "total_seconds": elapsed,
                "mean_milliseconds_per_update": 1000.0 * elapsed / args.repetitions,
                "implementation": "layered_scalar_reference_numpy",
            }
        )
    out_dir = ROOT / "results/runtime"
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "runtime_summary.csv", index=False)
    write_json(
        out_dir / "audit.json",
        {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "mode": args.mode,
            "claim_boundary": (
                "This benchmarks only the included NumPy layered reference, not a central beam-space SOCP or production O-RAN stack."
            ),
            "records": rows,
        },
    )
    print(df.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
