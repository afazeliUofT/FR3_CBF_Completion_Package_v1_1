from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt

from _bootstrap import ROOT
from fr3_cbf.io import load_yaml, write_json
from fr3_cbf.s1 import evaluate_s1


def resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def main() -> int:
    parser = argparse.ArgumentParser(description="Run P.530-19 fixed-link S1 adequacy screening")
    parser.add_argument("--config", default="config/s1_adequacy.yaml")
    parser.add_argument("--mode", choices=["demo", "real"])
    args = parser.parse_args()
    cfg = load_yaml(resolve(args.config))
    mode = args.mode or str(cfg.get("mode", "demo"))
    links_csv = resolve(cfg["input_links_csv"][mode])
    out_dir = resolve(cfg["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    details, summary, audit = evaluate_s1(
        links_csv=links_csv,
        candidate_i_over_n_db=[float(x) for x in cfg["candidate_i_over_n_db"]],
        mode=mode,
        p530_products_dir=resolve(cfg["p530_products_dir"]),
        global_allocation_pct=cfg.get("allocated_incremental_outage_pct"),
        use_all_percentages_method=bool(cfg.get("use_all_percentages_method", True)),
        require_real_grids=bool(cfg.get("require_real_p530_grids_for_real_mode", True)),
    )
    details.to_csv(out_dir / "link_details.csv", index=False)
    summary.to_csv(out_dir / "candidate_summary.csv", index=False)
    audit.update(
        {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "config": str(resolve(args.config)),
            "evidence_level": "DEMO" if mode == "demo" else "VALIDATED_MODEL_INPUT_PENDING_HUMAN_REVIEW",
            "strict_validity_checks": bool(cfg.get("strict_validity_checks", True)),
        }
    )
    write_json(out_dir / "audit.json", audit)

    fig, ax = plt.subplots(figsize=(8.0, 5.0))
    for link_id, group in details.groupby("link_id"):
        ax.plot(
            group["candidate_i_over_n_db"],
            group["incremental_outage_pct_worst_month"],
            marker="o",
            label=str(link_id),
        )
        allocation = float(group["allocated_incremental_outage_pct"].iloc[0])
        ax.axhline(allocation, linewidth=0.6, linestyle="--")
    ax.set_xlabel("Candidate short-term I/N cap (dB)")
    ax.set_ylabel("Incremental worst-month outage (%)")
    ax.set_title(f"S1 adequacy screen - {mode.upper()} mode")
    if details["link_id"].nunique() <= 12:
        ax.legend(fontsize=7)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_dir / "incremental_outage_vs_cap.png", dpi=180)
    plt.close(fig)

    provisional = float(cfg["provisional_candidate_to_freeze_db"])
    row = summary[summary["candidate_i_over_n_db"] == provisional]
    if row.empty:
        print(f"S1 RUN COMPLETE: provisional {provisional:g} dB was not tested")
    else:
        passed = bool(row.iloc[0]["all_links_pass"])
        print(f"S1 RUN COMPLETE: mode={mode}, provisional {provisional:g} dB allocation-pass={passed}")
    if mode == "demo":
        print("DEMO ONLY: do not freeze a regulatory/project decision from these results.")
    print(f"Outputs: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
