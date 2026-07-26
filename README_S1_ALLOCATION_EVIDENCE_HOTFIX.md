# S1 Allocation Evidence Hotfix

## Purpose

The terrain stage is complete. The only missing field in the frozen 70-link S1 table is:

```text
allocated_incremental_outage_pct
```

This hotfix performs the **next read-only evidence step**. It joins every frozen link back to its canonical TAFL TX and RX frequency records and exposes the equipment metadata needed for a defensible allocation decision.

It does **not** choose an allocation.

## Why an allocation cannot be guessed

ITU-R P.530 predicts the wanted fixed-link outage for a selected BER threshold and fade margin. It does not provide one universal incremental-outage allowance for every fixed link.

A standards-anchored allowance depends on the applicable performance framework and scenario, including matters such as:

- co-primary sharing versus another interference-source category;
- national access, short-haul, long-haul, or international network portion;
- G.826 or G.828 performance basis;
- the declared mapping from P.530 BER-threshold outage to the chosen error-performance parameter;
- operator or administration apportionment decisions.

Path length alone is not an authoritative network-function classifier.

## Install

Copy this ZIP to the package root and run:

```bash
unzip -o FR3_CBF_v1_1_S1_Allocation_Evidence_Hotfix.zip -d .
sha256sum -c S1_ALLOCATION_EVIDENCE_HOTFIX_MANIFEST.sha256
python3 -m py_compile scripts/03_7_build_s1_allocation_evidence.py
```

## Run

```bash
mkdir -p logs
set -o pipefail

python3 scripts/03_7_build_s1_allocation_evidence.py \
  --links data/real/paired_fs_links_before_allocation.csv \
  --tafl data/external/tafl_raw/canonical/TAFL_LTAF_Fixe.csv \
  --terrain-decision data/real/TERRAIN_DECISION.json \
  --pairing-decision data/real/TAFL_PAIRING_DECISION.json \
  --out-dir data/real/s1_allocation_review \
  --expected-links 70 \
  2>&1 | tee logs/03_7_s1_allocation_evidence.log

BUILD_EXIT=${PIPESTATUS[0]}
echo "Allocation-evidence exit code: $BUILD_EXIT"
test "$BUILD_EXIT" -eq 0 || exit "$BUILD_EXIT"
```

## Outputs

```text
data/real/s1_allocation_review/s1_allocation_review_unfinished.csv
data/real/s1_allocation_review/summary.json
data/real/s1_allocation_review/SUMMARY.md
data/real/s1_allocation_review/S1_ALLOCATION_EVIDENCE_AUDIT.json
```

The right-most decision columns in the CSV are intentionally blank.

## Inspect

```bash
python3 -m json.tool data/real/s1_allocation_review/summary.json

python3 - <<'PY'
import pandas as pd
p = "data/real/s1_allocation_review/s1_allocation_review_unfinished.csv"
df = pd.read_csv(p)
cols = [
    "link_id",
    "distance_km",
    "tx_analog_digital",
    "rx_analog_digital",
    "tx_digital_capacity_mbps",
    "rx_digital_capacity_mbps",
    "digital_capacity_consistent",
    "tx_occupied_bandwidth_khz",
    "rx_occupied_bandwidth_khz",
    "tx_modulation",
    "rx_modulation",
]
print(df[cols].to_string(index=False))
PY
```

## Stop condition

Do not create `data/real/paired_fs_links.csv` and do not run real S1 yet.

The next decision depends on the evidence output:

- **Preferred:** obtain operator/regulator-supported classifications and derive per-link allocations.
- **Fallback:** run explicitly labelled standards-anchored sensitivity scenarios, without claiming that either scenario is the final regulatory allocation.
