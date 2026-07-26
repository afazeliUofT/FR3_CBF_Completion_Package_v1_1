from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

REQUIRED = [
    "time_index", "incumbent_id", "sector_id", "tone_group", "frequency_ghz",
    "spectral_overlap_fraction", "path_gain_linear", "receiver_gain_linear",
    "element_gain_accounted", "clutter_treatment", "implementation_version", "provenance_note",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a P.452 coupling export without claiming to implement P.452")
    parser.add_argument("csv")
    args = parser.parse_args()
    df = pd.read_csv(args.csv)
    errors = []
    if df.empty:
        errors.append("No coupling rows found")
    missing = [c for c in REQUIRED if c not in df]
    if missing:
        errors.append(f"Missing columns: {missing}")
    else:
        for col in ["frequency_ghz", "spectral_overlap_fraction", "path_gain_linear", "receiver_gain_linear"]:
            values = pd.to_numeric(df[col], errors="coerce")
            if values.isna().any() or np.any(values < 0):
                errors.append(f"Invalid nonnegative numeric column: {col}")
        if np.any(pd.to_numeric(df["spectral_overlap_fraction"], errors="coerce") > 1):
            errors.append("spectral_overlap_fraction exceeds 1")
        if df["implementation_version"].fillna("").astype(str).str.strip().eq("").any():
            errors.append("Missing implementation_version")
        if df["provenance_note"].fillna("").astype(str).str.strip().eq("").any():
            errors.append("Missing provenance_note")
        normalized_gain_flag = df["element_gain_accounted"].astype(str).str.strip().str.lower()
        if not normalized_gain_flag.isin({"true", "false", "1", "0", "yes", "no"}).all():
            errors.append("element_gain_accounted must be an explicit boolean-like value")
        allowed = {"included_in_p452_profile", "separate_p2108", "none_documented"}
        unknown = set(df["clutter_treatment"].astype(str)) - allowed
        if unknown:
            errors.append(f"Unknown clutter_treatment values: {sorted(unknown)}")
    if errors:
        for error in errors:
            print("ERROR:", error)
        print("P.452 EXPORT VALIDATION: FAIL")
        return 1
    print(f"P.452 EXPORT VALIDATION: PASS ({len(df)} rows)")
    print("This validates interchange structure/provenance, not numerical correctness of the external implementation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
