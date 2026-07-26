#!/usr/bin/env python3
"""Build standards-anchored, explicitly conditional S1 allocation scenarios.

No final allocation is selected. The script converts the frozen link/equipment
record into a set of labelled ITU-R F.1565-1/G.826 SESR sensitivity cases. It
also writes canonical TAFL frequency-record IDs into every scenario file using
the already-audited resolution table.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from _bootstrap import ROOT


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def clean_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def as_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin(["true", "1", "yes"])


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def longhaul_a(distance_km: float, a1: float) -> tuple[float, float]:
    """Return (A, effective length) for F.1565-1 Table 6.

    The Recommendation uses Lmin=50 km for scaling. The first branch applies
    through 100 km; the second applies above 100 km.
    """
    if not math.isfinite(distance_km) or distance_km <= 0:
        raise ValueError(f"Invalid link distance: {distance_km}")
    if not (0.01 <= a1 <= 0.02):
        raise ValueError(f"A1 must be in the F.1565 provisional range [0.01, 0.02], got {a1}")
    effective_length = max(50.0, distance_km)
    if effective_length <= 100.0:
        a = (a1 + 0.002) * effective_length / 100.0
    else:
        a = a1 + 2.0e-5 * effective_length
    return a, effective_length


def scenario_allocation_percent(
    scenario: dict[str, Any], distances_km: pd.Series
) -> tuple[pd.Series, str]:
    formula = clean_text(scenario.get("formula"))
    source_factor = float(scenario.get("source_factor", 1.0))
    if source_factor not in {1.0, 0.1}:
        raise ValueError(f"Unsupported source_factor={source_factor}; expected 1.0 or 0.1")

    # F.1565 quantities are ratios. Multiply by 100 to write percent units
    # expected by the S1 code.
    if formula == "access_shorthaul":
        block_allowance = float(scenario["block_allowance"])
        if not (0.075 <= block_allowance <= 0.085):
            raise ValueError(
                f"B/C must be within the F.1565 provisional range [0.075, 0.085], got {block_allowance}"
            )
        ratio = 0.0002 * block_allowance * source_factor
        percent = ratio * 100.0
        values = pd.Series(percent, index=distances_km.index, dtype=float)
        derivation = (
            f"100*(0.0002*{block_allowance:g}*{source_factor:g}) = {percent:.12g}%"
        )
        return values, derivation

    if formula == "longhaul":
        a1 = float(scenario["a1"])
        values: list[float] = []
        for distance in distances_km.astype(float):
            a_value, _ = longhaul_a(float(distance), a1)
            values.append(100.0 * 0.0002 * a_value * source_factor)
        return pd.Series(values, index=distances_km.index, dtype=float), (
            "per-link: 100*0.0002*A*source_factor; "
            "A=(A1+0.002)*max(L,50)/100 for max(L,50)<=100 km, "
            "else A=A1+2e-5*L"
        )

    raise ValueError(f"Unsupported formula: {formula}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build conditional F.1565/G.826 S1 allocation scenario inputs"
    )
    parser.add_argument("--config", default="config/s1_allocation_matrix.yaml")
    args = parser.parse_args()

    cfg_path = resolve(args.config)
    cfg = load_yaml(cfg_path)
    inputs = cfg["inputs"]
    outputs = cfg["outputs"]

    links_path = resolve(inputs["links_before_allocation"])
    evidence_path = resolve(inputs["allocation_evidence"])
    resolution_path = resolve(inputs["source_id_resolution"])
    out_dir = resolve(outputs["scenario_input_dir"])
    expected_links = int(cfg["expected_links"])

    for path in [cfg_path, links_path, evidence_path, resolution_path]:
        if not path.is_file():
            raise FileNotFoundError(path)

    links = pd.read_csv(
        links_path,
        dtype={
            "link_id": str,
            "tx_source_record_id": str,
            "rx_source_record_id": str,
            "tafl_auth_number": str,
        },
    )
    evidence = pd.read_csv(
        evidence_path,
        dtype={
            "link_id": str,
            "tx_source_record_id_input": str,
            "rx_source_record_id_input": str,
            "tx_source_record_id": str,
            "rx_source_record_id": str,
        },
    )
    resolution = pd.read_csv(resolution_path, dtype=str)

    if len(links) != expected_links or links["link_id"].nunique() != expected_links:
        raise ValueError(f"Expected {expected_links} unique links, found {len(links)} rows/{links['link_id'].nunique()} IDs")
    if len(evidence) != expected_links or evidence["link_id"].nunique() != expected_links:
        raise ValueError("Allocation-evidence table does not contain the expected one-to-one link population")
    if len(resolution) != 2 * expected_links:
        raise ValueError(f"Expected {2 * expected_links} source-ID resolutions, found {len(resolution)}")
    if not as_bool(evidence["source_checks_pass"]).all():
        raise ValueError("At least one source-integrity check failed")
    if not as_bool(evidence["fully_digital_pair"]).all():
        raise ValueError("At least one retained pair is not confirmed digital at both endpoints")
    if not as_bool(evidence["digital_capacity_consistent"]).all():
        raise ValueError("At least one retained pair has inconsistent endpoint capacity")
    if not as_bool(evidence["occupied_bandwidth_consistent"]).all():
        raise ValueError("At least one retained pair has inconsistent occupied bandwidth")

    capacities = pd.to_numeric(evidence["tx_digital_capacity_mbps"], errors="coerce")
    if capacities.isna().any() or ((capacities < 1.5) | (capacities > 3500.0)).any():
        raise ValueError("F.1565/G.826 SESR scenario requires capacities within 1.5-3500 Mbit/s")

    merged = links.merge(
        evidence[
            [
                "link_id",
                "distance_km",
                "tx_source_record_id_input",
                "rx_source_record_id_input",
                "tx_source_record_id",
                "rx_source_record_id",
                "tx_digital_capacity_mbps",
                "tx_modulation",
                "tx_occupied_bandwidth_khz",
            ]
        ],
        on="link_id",
        how="left",
        validate="one_to_one",
        suffixes=("", "_evidence"),
    )
    if merged["distance_km"].isna().any():
        raise ValueError("Missing distance after one-to-one evidence merge")

    # Preserve legacy shortened values, then write canonical identifiers into
    # all scenario files. This does not alter link geometry or P.530 inputs.
    if "tx_source_record_id" in merged.columns:
        merged["tx_source_record_id_legacy"] = merged["tx_source_record_id"].astype(str)
    if "rx_source_record_id" in merged.columns:
        merged["rx_source_record_id_legacy"] = merged["rx_source_record_id"].astype(str)
    merged["tx_source_record_id"] = merged["tx_source_record_id_evidence"].astype(str)
    merged["rx_source_record_id"] = merged["rx_source_record_id_evidence"].astype(str)
    merged = merged.drop(
        columns=[
            c
            for c in ["tx_source_record_id_evidence", "rx_source_record_id_evidence"]
            if c in merged.columns
        ]
    )

    allocation_existing = pd.to_numeric(
        merged.get("allocated_incremental_outage_pct"), errors="coerce"
    )
    if allocation_existing.notna().any():
        raise ValueError("Input links already contain an allocation; expected the frozen pre-allocation table")

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_rows: list[dict[str, Any]] = []
    scenario_ids: set[str] = set()
    mapping_label = cfg["threshold_event_mapping"]["label"]
    mapping_status = cfg["threshold_event_mapping"]["status"]

    for scenario in cfg["scenarios"]:
        scenario_id = clean_text(scenario["id"])
        if not scenario_id or scenario_id in scenario_ids:
            raise ValueError(f"Blank or duplicate scenario id: {scenario_id!r}")
        scenario_ids.add(scenario_id)

        scenario_df = merged.copy()
        allocation, derivation = scenario_allocation_percent(
            scenario, pd.to_numeric(scenario_df["distance_km"], errors="raise")
        )
        if (~allocation.map(math.isfinite)).any() or (allocation <= 0).any():
            raise ValueError(f"Scenario {scenario_id} produced invalid allocations")

        scenario_df["allocated_incremental_outage_pct"] = allocation
        scenario_df["s1_allocation_scenario_id"] = scenario_id
        scenario_df["sharing_class"] = clean_text(scenario["sharing_class"])
        scenario_df["network_portion"] = clean_text(scenario["network_portion"])
        scenario_df["performance_basis"] = "ITU-R F.1565-1 / ITU-T G.826"
        scenario_df["performance_parameter"] = "SESR degradation sensitivity"
        scenario_df["ber_outage_mapping"] = mapping_label
        scenario_df["ber_outage_mapping_status"] = mapping_status
        scenario_df["allocation_derivation"] = derivation
        scenario_df["decision_source"] = (
            "ITU-R F.1565-1 Tables 6, 8 and 10; ITU-R F.1094-2 Y/Z source apportionment"
        )
        scenario_df["review_note"] = (
            "CONDITIONAL SENSITIVITY SCENARIO ONLY; not a frozen operator or regulatory allocation"
        )
        scenario_df["provenance_note"] = (
            scenario_df["provenance_note"].fillna("").astype(str).str.strip()
            + " | canonical TAFL IDs restored by unique audited mapping"
            + f" | conditional S1 scenario={scenario_id}"
        ).str.strip(" |")

        scenario_path = out_dir / f"{scenario_id}.csv"
        scenario_df.to_csv(scenario_path, index=False)
        scenario_record = {
            "scenario_id": scenario_id,
            "sharing_class": clean_text(scenario["sharing_class"]),
            "network_portion": clean_text(scenario["network_portion"]),
            "formula": clean_text(scenario["formula"]),
            "source_factor": float(scenario.get("source_factor", 1.0)),
            "block_allowance": scenario.get("block_allowance"),
            "a1": scenario.get("a1"),
            "allocation_min_pct": float(allocation.min()),
            "allocation_median_pct": float(allocation.median()),
            "allocation_max_pct": float(allocation.max()),
            "input_csv": str(scenario_path.relative_to(ROOT)),
            "input_sha256": sha256_file(scenario_path),
            "status": "CONDITIONAL_SENSITIVITY_NOT_FINAL_COMPLIANCE",
        }
        write_json(out_dir / f"{scenario_id}.json", scenario_record)
        manifest_rows.append(scenario_record)

    manifest = pd.DataFrame(manifest_rows).sort_values("scenario_id")
    manifest_path = out_dir / "scenario_manifest.csv"
    manifest.to_csv(manifest_path, index=False)
    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "config": str(cfg_path.relative_to(ROOT)),
        "config_sha256": sha256_file(cfg_path),
        "links_source": str(links_path.relative_to(ROOT)),
        "links_source_sha256": sha256_file(links_path),
        "allocation_evidence": str(evidence_path.relative_to(ROOT)),
        "allocation_evidence_sha256": sha256_file(evidence_path),
        "source_id_resolution": str(resolution_path.relative_to(ROOT)),
        "source_id_resolution_sha256": sha256_file(resolution_path),
        "link_count": expected_links,
        "scenario_count": len(manifest),
        "scenario_manifest": str(manifest_path.relative_to(ROOT)),
        "scenario_manifest_sha256": sha256_file(manifest_path),
        "final_allocation_selected": False,
        "claim_boundary": (
            "The files are standards-anchored conditional sensitivity cases. "
            "TAFL metadata does not establish network portion, current sharing class, "
            "or formal equivalence between BER=1e-3 fade exceedance and SESR."
        ),
    }
    write_json(out_dir / "SCENARIO_BUILD_AUDIT.json", audit)

    print("S1 ALLOCATION SCENARIO BUILD: PASS")
    print(f"Links: {expected_links}")
    print(f"Scenarios: {len(manifest)}")
    print(manifest[["scenario_id", "allocation_min_pct", "allocation_median_pct", "allocation_max_pct"]].to_string(index=False))
    print(f"Manifest: {manifest_path}")
    print("No final allocation was selected or frozen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
