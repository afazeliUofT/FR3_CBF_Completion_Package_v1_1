from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from _bootstrap import ROOT
from fr3_cbf.layered import proportional_sector_budgets, verify_sector_budgets


def main() -> int:
    parser = argparse.ArgumentParser(description="Allocate aggregate incumbent allowances to sectors")
    parser.add_argument("--contributions", required=True, help="CSV: incumbent_id,sector_id,nominal_contribution_w")
    parser.add_argument("--allowances", required=True, help="CSV: incumbent_id,total_allowance_w")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    contrib_df = pd.read_csv(args.contributions)
    allow_df = pd.read_csv(args.allowances)
    pivot = contrib_df.pivot(index="incumbent_id", columns="sector_id", values="nominal_contribution_w").fillna(0.0)
    allowances = allow_df.set_index("incumbent_id").loc[pivot.index, "total_allowance_w"].to_numpy(dtype=float)
    budgets = proportional_sector_budgets(pivot.to_numpy(dtype=float), allowances)
    verify_sector_budgets(budgets, allowances)
    rows = []
    for li, incumbent in enumerate(pivot.index):
        for bi, sector in enumerate(pivot.columns):
            rows.append({"incumbent_id": incumbent, "sector_id": sector, "budget_w": budgets[li, bi]})
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"Wrote certified-sum sector budgets to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
