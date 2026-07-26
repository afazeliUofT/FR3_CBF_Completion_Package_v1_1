from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _bootstrap import ROOT
from fr3_cbf.bundle import validate_bundle
from fr3_cbf.io import load_yaml, write_json


def resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def contributions_from_bundle(path: Path) -> tuple[np.ndarray, np.ndarray, dict]:
    validation = validate_bundle(path)
    with np.load(path, allow_pickle=False) as z:
        w = z["nominal_beamformers"]
        r = z["coupling"]
        thresholds = np.asarray(z["thresholds"], dtype=float)
        tone_weights = np.asarray(z["tone_weights"], dtype=float)
    if w.ndim != 4 or r.ndim != 5:
        raise ValueError("E1 requires a static bundle without a time axis")
    ell, b, t, _m, _ = r.shape
    contrib = np.zeros((ell, b), dtype=float)
    for l in range(ell):
        for bi in range(b):
            for ti in range(t):
                wb = w[bi, ti]
                contrib[l, bi] += tone_weights[ti] * float(np.real(np.trace(wb.conj().T @ r[l, bi, ti] @ wb)))
    return contrib, thresholds, validation


def main() -> int:
    parser = argparse.ArgumentParser(description="Run E1 static fixed-service continuity experiment")
    parser.add_argument("--config", default="config/e1_static_fs.yaml")
    parser.add_argument("--mode", choices=["demo", "real"])
    args = parser.parse_args()
    cfg = load_yaml(resolve(args.config))
    mode = args.mode or cfg.get("mode", "demo")
    bundle = resolve(cfg["input_bundle"][mode])
    if mode == "real" and "demo" in bundle.name.lower():
        raise SystemExit("Real mode points to a demo bundle")
    contrib, thresholds, validation = contributions_from_bundle(bundle)
    ell, b = contrib.shape
    reserve = float(cfg["controller"]["reserve_fraction"])

    full_ratio = contrib.sum(axis=1) / thresholds
    q_uniform = min(1.0, float(np.min(thresholds / np.maximum(contrib.sum(axis=1), 1e-30))))
    q_cbf = min(1.0, float(np.min((1.0 - reserve) * thresholds / np.maximum(contrib.sum(axis=1), 1e-30))))
    q_hard = 0.35
    method_q = {
        "unprotected": 1.0,
        "hard_backoff": q_hard,
        "static_cap": q_uniform,
        "cbf": q_cbf,
    }
    rows = []
    snr = 15.0
    for method in cfg["methods"]:
        q = method_q[method]
        ratios = contrib.sum(axis=1) * q / thresholds
        rows.append(
            {
                "method": method,
                "sector_power_scale": q,
                "max_normalized_interference": float(ratios.max()),
                "mean_normalized_interference": float(ratios.mean()),
                "protected_all_incumbents": bool(np.all(ratios <= 1.0 + 1e-12)),
                "utility_proxy": float(b * np.log2(1.0 + snr * q)),
            }
        )
    result = pd.DataFrame(rows)
    out_dir = resolve(cfg["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_dir / "summary.csv", index=False)
    write_json(
        out_dir / "audit.json",
        {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "evidence_level": "DEMO" if mode == "demo" else "MODEL_RUN_REQUIRES_HUMAN_REVIEW",
            "bundle_validation": validation,
            "full_scale_normalized_interference": full_ratio.tolist(),
            "method_note": "Reference sector-power-scale comparison; not the full beam-space SOCP.",
        },
    )

    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    ax.bar(result["method"], result["max_normalized_interference"])
    ax.axhline(1.0, linestyle="--", label="protection boundary")
    ax.set_ylabel("Maximum normalized incumbent interference")
    ax.set_title(f"E1 static protection - {mode.upper()}")
    ax.tick_params(axis="x", rotation=20)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "normalized_interference.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    ax.bar(result["method"], result["utility_proxy"])
    ax.set_ylabel("Utility proxy")
    ax.set_title(f"E1 utility/protection comparison - {mode.upper()}")
    ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    fig.savefig(out_dir / "utility_proxy.png", dpi=180)
    plt.close(fig)
    print(f"E1 COMPLETE: mode={mode}, outputs={out_dir}")
    if mode == "demo":
        print("DEMO ONLY: replace the bundle with real Sionna beams and validated P.452 coupling.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
