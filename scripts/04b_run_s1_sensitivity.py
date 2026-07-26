from __future__ import annotations

import argparse
import itertools
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from _bootstrap import ROOT
from fr3_cbf.io import load_yaml, write_json
from fr3_cbf.s1 import evaluate_s1


def resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def main() -> int:
    parser = argparse.ArgumentParser(description="Run predeclared S1 sensitivity grid")
    parser.add_argument("--config", default="config/s1_adequacy.yaml")
    parser.add_argument("--mode", choices=["demo", "real"])
    args = parser.parse_args()
    cfg = load_yaml(resolve(args.config))
    mode = args.mode or str(cfg.get("mode", "demo"))
    links_csv = resolve(cfg["input_links_csv"][mode])
    out_dir = resolve(cfg["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    nominal_details, _, nominal_audit = evaluate_s1(
        links_csv,
        [float(x) for x in cfg["candidate_i_over_n_db"]],
        mode,
        resolve(cfg["p530_products_dir"]),
        cfg.get("allocated_incremental_outage_pct"),
        bool(cfg.get("use_all_percentages_method", True)),
        bool(cfg.get("require_real_p530_grids_for_real_mode", True)),
    )
    source_df = pd.read_csv(links_csv)
    nominal_k = nominal_details.groupby("link_id")["k_percent"].first().to_dict()
    nominal_dn = nominal_details.groupby("link_id")["dn75_n_units"].first().to_dict()

    sens = cfg["sensitivity"]
    combinations = list(
        itertools.product(
            sens["fade_margin_offsets_db"],
            sens["mean_terrain_offsets_m"],
            sens["dn75_scale"],
            sens["logk_offsets"],
        )
    )
    rows: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="fr3_s1_sensitivity_") as td:
        for index, (fm_offset, terrain_offset, dn_scale, logk_offset) in enumerate(combinations):
            df = source_df.copy()
            df["fade_margin_db"] = pd.to_numeric(df["fade_margin_db"]) + float(fm_offset)
            df["mean_terrain_elevation_m_asl"] = pd.to_numeric(df["mean_terrain_elevation_m_asl"]) + float(terrain_offset)
            df["k_override_percent"] = [nominal_k[str(x)] * 10.0 ** float(logk_offset) for x in df["link_id"]]
            df["dn75_override_n_units"] = [nominal_dn[str(x)] * float(dn_scale) for x in df["link_id"]]
            temp_csv = Path(td) / f"scenario_{index:04d}.csv"
            df.to_csv(temp_csv, index=False)
            details, summary, _ = evaluate_s1(
                temp_csv,
                [float(x) for x in cfg["candidate_i_over_n_db"]],
                mode,
                None,
                cfg.get("allocated_incremental_outage_pct"),
                bool(cfg.get("use_all_percentages_method", True)),
                False,
            )
            for _, srow in summary.iterrows():
                rows.append(
                    {
                        "scenario_id": index,
                        "fade_margin_offset_db": float(fm_offset),
                        "mean_terrain_offset_m": float(terrain_offset),
                        "dn75_scale": float(dn_scale),
                        "logk_offset": float(logk_offset),
                        "candidate_i_over_n_db": float(srow.candidate_i_over_n_db),
                        "all_links_pass": bool(srow.all_links_pass),
                        "worst_incremental_outage_pct": float(srow.worst_incremental_outage_pct),
                        "minimum_allocation_margin_pct": float(srow.minimum_allocation_margin_pct),
                        "links_with_warnings": int(srow.links_with_warnings),
                    }
                )

    result = pd.DataFrame(rows)
    result.to_csv(out_dir / "sensitivity_scenarios.csv", index=False)
    summary = (
        result.groupby("candidate_i_over_n_db", as_index=False)
        .agg(
            all_scenarios_pass=("all_links_pass", "all"),
            scenario_count=("scenario_id", "nunique"),
            worst_incremental_outage_pct=("worst_incremental_outage_pct", "max"),
            minimum_allocation_margin_pct=("minimum_allocation_margin_pct", "min"),
            scenarios_with_warnings=("links_with_warnings", lambda x: int((x > 0).sum())),
        )
        .sort_values("candidate_i_over_n_db")
    )
    summary.to_csv(out_dir / "sensitivity_summary.csv", index=False)
    write_json(
        out_dir / "sensitivity_audit.json",
        {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "source_input": str(links_csv),
            "nominal_p530_products_loaded": nominal_audit["p530_products_loaded"],
            "scenario_count": len(combinations),
            "sensitivity_definition": sens,
            "summary": summary.to_dict(orient="records"),
        },
    )
    print(f"S1 SENSITIVITY COMPLETE: {len(combinations)} scenarios; outputs={out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
