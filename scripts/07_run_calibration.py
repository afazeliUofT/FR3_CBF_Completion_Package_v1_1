from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _bootstrap import ROOT
from fr3_cbf.calibration import evaluate_split_conformal, wilson_interval
from fr3_cbf.io import load_yaml, sha256_file, write_json


def resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def main() -> int:
    parser = argparse.ArgumentParser(description="Run split-conformal residual calibration")
    parser.add_argument("--config", default="config/calibration.yaml")
    parser.add_argument("--mode", choices=["demo", "real"])
    args = parser.parse_args()
    cfg = load_yaml(resolve(args.config))
    mode = args.mode or cfg.get("mode", "demo")
    path = resolve(cfg["input_csv"][mode])
    df = pd.read_csv(path)
    score_col = cfg["score_column"]
    if score_col not in df:
        raise ValueError(f"Missing score column {score_col}")
    rng = np.random.default_rng(int(cfg["seed"]))
    indices = rng.permutation(len(df))
    n_cal = int(np.floor(float(cfg["calibration_fraction"]) * len(df)))
    if n_cal < 1 or n_cal >= len(df):
        raise ValueError("Calibration split leaves an empty partition")
    cal = df.iloc[indices[:n_cal]]
    test = df.iloc[indices[n_cal:]]
    alpha = float(cfg["miscoverage_alpha"])
    overall = evaluate_split_conformal(cal[score_col].to_numpy(), test[score_col].to_numpy(), alpha)

    overall_ci = wilson_interval(overall.covered_count, overall.test_size, confidence=0.95)
    strata = []
    stratum_col = cfg.get("stratum_column")
    minimum = int(cfg.get("minimum_test_points_per_stratum", 20))
    if stratum_col and stratum_col in test:
        for name, group in test.groupby(stratum_col):
            values = group[score_col].to_numpy(dtype=float)
            covered = int(np.sum(values <= overall.quantile))
            coverage = covered / len(group)
            ci_low, ci_high = wilson_interval(covered, len(group), confidence=0.95)
            strata.append(
                {
                    "stratum": str(name),
                    "test_size": len(group),
                    "covered_count": covered,
                    "empirical_coverage": coverage,
                    "wilson_95_low": ci_low,
                    "wilson_95_high": ci_high,
                    "minimum_size_met": len(group) >= minimum,
                }
            )

    out_dir = resolve(cfg["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(strata).to_csv(out_dir / "stratified_coverage.csv", index=False)
    record = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "input": str(path),
        "input_sha256": sha256_file(path),
        "alpha": alpha,
        "quantile": overall.quantile,
        "calibration_size": overall.calibration_size,
        "test_size": overall.test_size,
        "target_coverage": overall.target_coverage,
        "covered_count": overall.covered_count,
        "empirical_coverage": overall.empirical_coverage,
        "wilson_95_low": overall_ci[0],
        "wilson_95_high": overall_ci[1],
        "strata": strata,
        "claim_boundary": (
            "Synthetic/demo calibration covers only the synthetic data-generating world."
            if mode == "demo"
            else "Coverage applies under the declared exchangeability/epoch assumptions and data domain."
        ),
    }
    write_json(out_dir / "calibration_report.json", record)

    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    sorted_scores = np.sort(test[score_col].to_numpy())
    ax.plot(sorted_scores, np.arange(1, len(sorted_scores) + 1) / len(sorted_scores))
    ax.axvline(overall.quantile, linestyle="--", label="calibrated margin")
    ax.set_xlabel("Absolute residual score")
    ax.set_ylabel("Empirical CDF")
    ax.set_title(f"Held-out residual coverage - {mode.upper()}")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "coverage_cdf.png", dpi=180)
    plt.close(fig)
    print(f"CALIBRATION COMPLETE: coverage={overall.empirical_coverage:.4f}, target={overall.target_coverage:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
