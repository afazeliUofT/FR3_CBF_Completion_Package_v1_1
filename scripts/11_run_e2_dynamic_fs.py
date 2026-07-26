from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _bootstrap import ROOT
from fr3_cbf.io import load_yaml, write_json
from fr3_cbf.safety import (
    EMAMarginGovernor,
    cbf_scale,
    hard_backoff_scale,
    myopic_scale,
    static_cap_scale,
    unprotected_scale,
    virtual_queue_scale,
)


def resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def demo_coupling(cfg: dict) -> np.ndarray:
    h = int(cfg["horizon_slots"])
    start = int(cfg["scenario"]["disturbance_start_slot"])
    peak_slot = int(cfg["scenario"]["disturbance_peak_slot"])
    c0 = float(cfg["scenario"]["nominal_coupling"])
    peak = float(cfg["scenario"]["peak_coupling"])
    c = np.full(h, c0, dtype=float)
    # Known/screened activation creates a jump; later loading/geometric drift is gradual.
    jump = min(peak, c0 + 0.50)
    c[start:] = jump
    if peak_slot > start:
        c[start:peak_slot + 1] = np.linspace(jump, peak, peak_slot - start + 1)
    tail_end = min(h, peak_slot + max(40, h // 4))
    if tail_end > peak_slot + 1:
        c[peak_slot:tail_end] = np.linspace(peak, c0 * 1.05, tail_end - peak_slot)
    c[tail_end:] = c0 * 1.05
    return c


def main() -> int:
    parser = argparse.ArgumentParser(description="Run E2 dynamic rate-limit trap experiment")
    parser.add_argument("--config", default="config/e2_dynamic_fs.yaml")
    parser.add_argument("--mode", choices=["demo", "real"])
    args = parser.parse_args()
    cfg = load_yaml(resolve(args.config))
    mode = args.mode or cfg.get("mode", "demo")
    if mode == "real":
        path = ROOT / "data/real/e2_coupling.csv"
        if not path.exists():
            raise SystemExit("Real mode requires data/real/e2_coupling.csv with columns time_s,coupling_at_full_scale")
        raw = pd.read_csv(path)
        coupling = raw["coupling_at_full_scale"].to_numpy(dtype=float)
        time_s = raw["time_s"].to_numpy(dtype=float)
    else:
        coupling = demo_coupling(cfg)
        time_s = np.arange(len(coupling), dtype=float) * float(cfg["slot_duration_s"])

    threshold = float(cfg["protection"]["threshold_linear"])
    delta = float(cfg["controller"]["max_scale_change_per_slot"])
    reserve = float(cfg["controller"]["reserve_fraction"])
    nu = float(cfg["scenario"]["uncertainty_drift_per_slot"])
    alpha = float(cfg["controller"]["ema_alpha"])
    gamma = float(cfg["controller"]["cbf_gamma"])
    methods = list(cfg["methods"])
    peak = float(np.max(coupling))

    records = []
    for method in methods:
        q_prev = 1.0
        queue = 0.0
        governor = EMAMarginGovernor(threshold, alpha, gamma, reserve * threshold, 0.0)
        for k, c_now in enumerate(coupling):
            nominal = 1.0
            if method == "unprotected":
                q = unprotected_scale(nominal, q_prev, delta)
            elif method == "hard_backoff":
                q = hard_backoff_scale(nominal, q_prev, delta, fixed_scale=0.35)
            elif method == "static_cap":
                q = static_cap_scale(nominal, q_prev, peak, threshold, delta)
            elif method == "myopic":
                q = myopic_scale(nominal, q_prev, c_now, threshold, delta)
            elif method == "virtual_queue":
                q, queue = virtual_queue_scale(nominal, q_prev, c_now, threshold, queue, delta)
            elif method == "cbf":
                next_actual = coupling[min(k + 1, len(coupling) - 1)]
                coupling_upper_next = max(next_actual, c_now + nu)
                ema_allow = max(0.0, governor.allowance())
                effective_threshold = min(threshold, ema_allow if np.isfinite(ema_allow) else threshold)
                q = cbf_scale(nominal, q_prev, coupling_upper_next, effective_threshold, delta, reserve)
            else:
                raise ValueError(method)
            interference = c_now * q
            governor.update(interference)
            utility = float(np.log2(1.0 + 15.0 * q))
            records.append(
                {
                    "method": method,
                    "slot": k,
                    "time_s": time_s[k],
                    "coupling_at_full_scale": c_now,
                    "power_scale": q,
                    "normalized_interference": interference / threshold,
                    "utility_proxy": utility,
                    "ema_state": governor.state,
                    "ema_margin": governor.margin,
                    "exceeded": interference > threshold + 1e-12,
                }
            )
            q_prev = q

    df = pd.DataFrame(records)
    summary = (
        df.groupby("method", as_index=False)
        .agg(
            maximum_normalized_interference=("normalized_interference", "max"),
            exceedance_fraction=("exceeded", "mean"),
            mean_utility_proxy=("utility_proxy", "mean"),
            minimum_power_scale=("power_scale", "min"),
            mean_filter_activity=("power_scale", lambda x: float(np.mean(np.abs(x.to_numpy() - 1.0)))),
        )
        .sort_values("method")
    )
    out_dir = resolve(cfg["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "trajectories.csv", index=False)
    summary.to_csv(out_dir / "summary.csv", index=False)
    write_json(
        out_dir / "audit.json",
        {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "evidence_level": "DEMO" if mode == "demo" else "MODEL_RUN_REQUIRES_HUMAN_REVIEW",
            "timing": (
                "At slot k the CBF uses a one-step upper coupling set before selecting the rate-limited action; "
                "the myopic controller uses only the current coupling."
            ),
            "summary": summary.to_dict(orient="records"),
        },
    )

    for column, ylabel, filename in [
        ("normalized_interference", "Normalized interference", "interference_trajectory.png"),
        ("power_scale", "Sector power scale", "power_scale_trajectory.png"),
        ("utility_proxy", "Utility proxy", "utility_trajectory.png"),
    ]:
        fig, ax = plt.subplots(figsize=(9.0, 4.8))
        for method, group in df.groupby("method"):
            ax.plot(group["time_s"], group[column], label=method)
        if column == "normalized_interference":
            ax.axhline(1.0, linestyle="--", label="protection boundary")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel(ylabel)
        ax.set_title(f"E2 dynamic aggregate stress - {mode.upper()}")
        ax.grid(True, alpha=0.25)
        ax.legend(ncol=2, fontsize=8)
        fig.tight_layout()
        fig.savefig(out_dir / filename, dpi=180)
        plt.close(fig)
    print(f"E2 COMPLETE: mode={mode}, outputs={out_dir}")
    if mode == "demo":
        print("DEMO ONLY: replace the synthetic coupling trajectory with validated dynamic coupling.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
