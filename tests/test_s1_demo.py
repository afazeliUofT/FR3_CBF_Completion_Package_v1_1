from pathlib import Path

from fr3_cbf.s1 import evaluate_s1


def test_demo_s1_runs():
    root = Path(__file__).resolve().parents[1]
    details, summary, audit = evaluate_s1(
        root / "data/demo/synthetic_paired_fs_links.csv",
        [10.0, 19.0],
        "demo",
        None,
        None,
        True,
        False,
    )
    assert len(details) == 6
    assert len(summary) == 2
    assert audit["mode"] == "demo"


def test_s1_marks_exhausted_fade_margin_as_full_outage(tmp_path):
    import pandas as pd
    from fr3_cbf.s1 import evaluate_s1

    row = pd.read_csv("data/demo/synthetic_paired_fs_links.csv").iloc[[0]].copy()
    row["fade_margin_db"] = 1.0
    row["allocated_incremental_outage_pct"] = 100.0
    path = tmp_path / "links.csv"
    row.to_csv(path, index=False)
    details, _, _ = evaluate_s1(
        path,
        [19.0],
        "demo",
        None,
        None,
        True,
        False,
    )
    assert details.iloc[0]["after_outage_pct_worst_month"] == 100.0
    assert details.iloc[0]["effective_fade_margin_raw_db"] < 0.0
