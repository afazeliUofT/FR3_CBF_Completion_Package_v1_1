from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _bootstrap import ROOT
from fr3_cbf.io import load_yaml, write_json
from fr3_cbf.safety import ExceedanceBudget, cbf_scale, myopic_scale, unprotected_scale
from fr3_cbf.units import dbw_to_w, w_to_dbw


def resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def demo_pass(cfg: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    h = int(cfg["horizon_slots"])
    dt = float(cfg["slot_duration_s"])
    center = float(cfg["scenario"]["demo_pass_center_slot"])
    width = float(cfg["scenario"]["demo_pass_width_slots"])
    k = np.arange(h, dtype=float)
    elevation = 5.0 + 70.0 * np.exp(-0.5 * ((k - center) / width) ** 2)
    # A normalized full-scale aggregate coupling proxy that rises as the tracked beam
    # rotates near the cellular deployment. It is a software demo, not a propagation claim.
    ratio = 0.35 + 1.55 * np.exp(-0.5 * ((k - center) / (0.65 * width)) ** 2)
    return k * dt, elevation, ratio


def main() -> int:
    parser = argparse.ArgumentParser(description="Run E3 drifting earth-station geometry experiment")
    parser.add_argument("--config", default="config/e3_tracking_eess.yaml")
    parser.add_argument("--mode", choices=["demo", "real"])
    args = parser.parse_args()
    cfg = load_yaml(resolve(args.config))
    mode = args.mode or cfg.get("mode", "demo")
    long_w = dbw_to_w(float(cfg["protection"]["long_term_threshold_dbw_per_10mhz"]))
    short_w = dbw_to_w(float(cfg["protection"]["short_term_threshold_dbw_per_10mhz"]))

    if mode == "real":
        path = ROOT / "data/real/e3_coupling.csv"
        if not path.exists():
            raise SystemExit(
                "Real mode requires data/real/e3_coupling.csv with time_s,elevation_deg,coupling_w_at_full_scale"
            )
        raw = pd.read_csv(path)
        time_s = raw["time_s"].to_numpy(dtype=float)
        elevation = raw["elevation_deg"].to_numpy(dtype=float)
        coupling_w = raw["coupling_w_at_full_scale"].to_numpy(dtype=float)
    else:
        time_s, elevation, ratio = demo_pass(cfg)
        coupling_w = long_w * ratio

    delta = float(cfg["controller"]["max_scale_change_per_slot"])
    reserve = float(cfg["controller"]["reserve_fraction"])
    methods = list(cfg["methods"])
    records = []
    allowed_fraction = float(cfg["protection"]["long_term_exceedance_fraction"])
    for method in methods:
        q_prev = 1.0
        budget = ExceedanceBudget(allowed_fraction=allowed_fraction, balance=0.0, maximum_balance=1.0)
        for k, coupling in enumerate(coupling_w):
            token_authorized = False
            token_violation = False
            next_coupling = coupling_w[min(k + 1, len(coupling_w) - 1)]
            if elevation[k] < float(cfg["scenario"]["minimum_elevation_deg"]):
                # Outside the protected tracking window in this case definition.
                q = unprotected_scale(1.0, q_prev, delta)
            elif method == "unprotected":
                q = unprotected_scale(1.0, q_prev, delta)
            elif method == "myopic":
                q = myopic_scale(1.0, q_prev, coupling, long_w, delta)
            elif method == "cbf":
                upper_next = max(coupling, next_coupling)
                # A long-threshold exceedance token is used only if the action can return
                # to the long safe set in the next slot under the same slew limit.
                if budget.can_exceed():
                    relaxed = cbf_scale(1.0, q_prev, upper_next, short_w, delta, 0.0)
                    next_long_target = min(1.0, (1.0 - reserve) * long_w / max(next_coupling, 1e-300))
                    token_authorized = relaxed - delta <= next_long_target + 1e-12
                allowed_threshold = short_w if token_authorized else long_w
                q = cbf_scale(1.0, q_prev, upper_next, allowed_threshold, delta, reserve if not token_authorized else 0.0)
            else:
                raise ValueError(method)
            interference = coupling * q
            long_exceeded = interference > long_w + 1e-30
            if method == "cbf" and elevation[k] >= float(cfg["scenario"]["minimum_elevation_deg"]):
                try:
                    budget.update(long_exceeded)
                except ValueError:
                    token_violation = True
            records.append(
                {
                    "method": method,
                    "slot": k,
                    "time_s": time_s[k],
                    "elevation_deg": elevation[k],
                    "protected_window": bool(elevation[k] >= float(cfg["scenario"]["minimum_elevation_deg"])),
                    "full_scale_coupling_dbw": w_to_dbw(max(coupling, 1e-300)),
                    "power_scale": q,
                    "interference_dbw": w_to_dbw(max(interference, 1e-300)),
                    "long_threshold_dbw": float(cfg["protection"]["long_term_threshold_dbw_per_10mhz"]),
                    "short_threshold_dbw": float(cfg["protection"]["short_term_threshold_dbw_per_10mhz"]),
                    "long_exceeded": long_exceeded,
                    "short_exceeded": interference > short_w + 1e-30,
                    "token_authorized": token_authorized,
                    "token_balance": budget.balance if method == "cbf" else np.nan,
                    "token_violation": token_violation,
                    "utility_proxy": float(np.log2(1.0 + 15.0 * q)),
                }
            )
            q_prev = q

    df = pd.DataFrame(records)
    summary_rows = []
    for method, group in df.groupby("method", sort=True):
        protected = group[group["protected_window"]]
        if protected.empty:
            long_fraction = float("nan")
            short_fraction = float("nan")
            max_protected_dbw = float("nan")
        else:
            long_fraction = float(protected["long_exceeded"].mean())
            short_fraction = float(protected["short_exceeded"].mean())
            max_protected_dbw = float(protected["interference_dbw"].max())
        summary_rows.append(
            {
                "method": method,
                "protected_slot_count": int(len(protected)),
                "long_exceedance_fraction_protected": long_fraction,
                "short_exceedance_fraction_protected": short_fraction,
                "maximum_interference_dbw_protected": max_protected_dbw,
                "long_exceedance_fraction_full_horizon": float(group["long_exceeded"].mean()),
                "mean_utility_proxy": float(group["utility_proxy"].mean()),
                "minimum_power_scale": float(group["power_scale"].min()),
                "token_violation_count": int(group["token_violation"].sum()),
            }
        )
    summary = pd.DataFrame(summary_rows).sort_values("method")
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
            "short_term_policy": cfg["protection"]["short_term_policy_first_paper"],
            "summary": summary.to_dict(orient="records"),
        },
    )

    fig, ax = plt.subplots(figsize=(9.0, 4.8))
    for method, group in df.groupby("method"):
        ax.plot(group["time_s"], group["interference_dbw"], label=method)
    ax.axhline(float(cfg["protection"]["long_term_threshold_dbw_per_10mhz"]), linestyle="--", label="long entry")
    ax.axhline(float(cfg["protection"]["short_term_threshold_dbw_per_10mhz"]), linestyle=":", label="short entry")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Aggregate interference at antenna output (dBW/10 MHz)")
    ax.set_title(f"E3 drifting earth-station geometry - {mode.upper()}")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "interference_trajectory.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9.0, 4.8))
    for method, group in df.groupby("method"):
        ax.plot(group["time_s"], group["power_scale"], label=method)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Sector/network power scale")
    ax.set_title(f"E3 control action - {mode.upper()}")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "power_scale_trajectory.png", dpi=180)
    plt.close(fig)
    print(f"E3 COMPLETE: mode={mode}, outputs={out_dir}")
    if mode == "demo":
        print("DEMO ONLY: use archived TLE, documented station pattern, and validated coupling for paper evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
