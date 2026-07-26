# FR3 CBF v1.1 — TAFL source-record ID preservation hotfix

## Defect corrected

The original pairing-freeze script read `gta_eligible_exact_pairs.csv` with
pandas dtype inference. Numeric-looking TAFL identifiers could therefore lose
leading zeroes before being written to the frozen link tables. The original
S1-allocation evidence script then required exact string equality with the
canonical TAFL `freq_rec_id`, causing all affected records to appear missing.

## Files

- `scripts/03_2_freeze_tafl_gta_pairs.py`
  - preserves TAFL record and authorization identifiers as strings for future
    clean rebuilds.
- `scripts/03_7_build_s1_allocation_evidence.py`
  - first attempts exact identifier matching;
  - otherwise permits only a **unique** decimal-normalized recovery;
  - rejects unresolved or ambiguous mappings;
  - writes `source_record_id_resolution.csv` with every input-to-canonical map;
  - verifies role, frequency, authorization, service, and subservice after
    canonical resolution;
  - does not choose or populate an outage allocation.

## Immediate-use boundary

For an already frozen terrain dataset, install the patched `03_7` script and
rerun the evidence stage. It is not necessary to rerun terrain because the
hotfix does not modify coordinates, link geometry, fade margin, or terrain. It
performs a read-only, one-to-one join to the canonical TAFL source and records
the mapping.

For a future clean package rebuild, use the patched `03_2` script and rerun the
pairing freeze so leading zeroes are preserved in the frozen link table from
the beginning.

## Mandatory pass conditions

The allocation-evidence run may proceed only when all of the following hold:

- exit code is zero;
- `link_count == 70`;
- `source_checks_pass_count == 70`;
- `source_record_id_count == 140`;
- `source_record_id_exact_match_count + source_record_id_normalized_match_count == 140`;
- `source_record_id_resolution.csv` has 140 rows;
- canonical IDs in that file are unique;
- no allocation decision field is populated.

A unique normalized recovery is not a heuristic partner selection. The TX/RX
pairing was already frozen. This hotfix only restores the exact canonical
identifier string after a legacy CSV representation loss, and it refuses every
ambiguous mapping.
