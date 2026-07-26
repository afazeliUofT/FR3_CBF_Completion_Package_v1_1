# FR3 CBF v1.1 — MRDEM Terrain Completion Hotfix

This hotfix closes the next data blocker after the 70-link TAFL pairing freeze:
`mean_terrain_elevation_m_asl` for the P.530-19 wanted-link adequacy gate.

The primary source is the official Natural Resources Canada Medium Resolution
Digital Elevation Model (MRDEM) **Digital Terrain Model (DTM)**. MRDEM provides a
30 m DTM and is referenced to CGVD2013. A DTM is selected rather than the DSM or
hillshade because P.530-19 defines `h_t` as mean terrain elevation along the path,
excluding trees.

## Evidence boundary

- P.530-19 does not prescribe a discrete endpoint-sample convention. The workflow
  computes and records both inclusive and interior-sample means. The value written
  to the link table is selected explicitly with `--mean-convention`; the recommended
  primary convention is `inclusive`, the literal sampled line mean.
- MRDEM is referenced to CGVD2013. TAFL supplies antenna/site elevations above mean
  sea level, but this workflow does not assert that the TAFL realization is identical
  to CGVD2013. Keep the predeclared ±10 m terrain sensitivity in `s1_adequacy.yaml`.
- The output still lacks an approved incremental-outage allocation. Do not run the
  real S1 validator until that separate decision is documented.

## Install

From the completion-package root:

```bash
unzip -o FR3_CBF_v1_1_MRDEM_Terrain_Hotfix.zip -d .
python3 -m pip install -r requirements-terrain.txt
```

## 1. Discover, download and crop the official MRDEM DTM

```bash
python3 scripts/03_3_fetch_mrdem_dtm.py \
  --links data/real/paired_fs_links_before_terrain.csv \
  --out-dir data/external/mrdem \
  --padding-deg 0.05
```

Do not continue unless the terminal begins its final block with:

```text
MRDEM FETCH/CROP: PASS
```

The script records the Open Government metadata, selected DTM VRT resource,
requested bounding box and SHA-256 hashes. It rejects DSM and hillshade resources.

## 2. Compute geodesic terrain profiles and the P.530 terrain mean

```bash
rm -rf data/real/terrain_review

python3 scripts/03_4_add_mrdem_terrain_profiles.py \
  --links data/real/paired_fs_links_before_terrain.csv \
  --dem data/external/mrdem/mrdem_dtm_study_subset.tif \
  --output data/real/paired_fs_links_with_terrain.csv \
  --out-dir data/real/terrain_review \
  --spacing-m 30 \
  --mean-convention inclusive \
  --expected-links 70
```

Do not continue unless it prints:

```text
TERRAIN PROFILE BUILD: PASS
```

The workflow retains:

- every geodesic profile sample;
- inclusive and interior-sample means;
- their difference;
- endpoint DEM ground heights;
- implied TAFL antenna heights above the DEM terrain;
- explicit QC flags and a complete audit JSON.

## 3. Generate the 70-page human-review PDF

```bash
python3 scripts/03_5_plot_mrdem_terrain_profiles.py \
  --profiles data/real/terrain_review/terrain_profile_samples.csv.gz \
  --summary data/real/terrain_review/terrain_summary.csv \
  --output data/real/terrain_review/terrain_profiles_review.pdf
```

Review every page. Check for:

- missing/void or implausible elevations;
- abrupt tile or datum steps;
- endpoints inconsistent with the recorded antenna altitudes;
- a path outside the expected geographic corridor;
- unusual water/shoreline behaviour;
- any row listed with `qc_flag_count > 0`.

Inspect the concise tables:

```bash
python3 - <<'PY'
import pandas as pd

s = pd.read_csv("data/real/terrain_review/terrain_summary.csv")
print("\nTERRAIN SUMMARY")
print(s.to_string(index=False))
print("\nFLAGGED LINKS")
print(s.loc[s["qc_flag_count"] > 0].to_string(index=False))
PY
```

## 4. Run terrain-freeze preflight

When every profile has been reviewed:

```bash
python3 scripts/03_6_freeze_mrdem_terrain.py \
  --links data/real/paired_fs_links_with_terrain.csv \
  --summary data/real/terrain_review/terrain_summary.csv \
  --profiles data/real/terrain_review/terrain_profile_samples.csv.gz \
  --audit data/real/terrain_review/TERRAIN_AUDIT.json \
  --review-pdf data/real/terrain_review/terrain_profiles_review.pdf \
  --reviewer "Ali Fazeli" \
  --expected-links 70
```

Expected ending:

```text
TERRAIN FREEZE PREFLIGHT: PASS
No files were written because --confirm was not supplied.
```

If any links have QC flags, correct the source/problem first. Only when each flag
has been explicitly reviewed and accepted may the same preflight be rerun with
`--accept-reviewed-flags`.

## 5. Freeze the reviewed terrain stage

Use a specific review note; do not write only “looks good”. For example:

```bash
python3 scripts/03_6_freeze_mrdem_terrain.py \
  --links data/real/paired_fs_links_with_terrain.csv \
  --summary data/real/terrain_review/terrain_summary.csv \
  --profiles data/real/terrain_review/terrain_profile_samples.csv.gz \
  --audit data/real/terrain_review/TERRAIN_AUDIT.json \
  --review-pdf data/real/terrain_review/terrain_profiles_review.pdf \
  --reviewer "Ali Fazeli" \
  --review-note "Reviewed all 70 MRDEM DTM profiles, endpoint elevations, inclusive/interior mean differences, and every listed QC flag; no unresolved terrain defect remains." \
  --expected-links 70 \
  --confirm
```

If the preflight reported flags that were genuinely reviewed and accepted, add:

```text
--accept-reviewed-flags
```

The freeze writes:

```text
data/real/paired_fs_links_before_allocation.csv
data/real/TERRAIN_DECISION.json
data/real/TERRAIN_DECISION.md
```

It intentionally leaves `allocated_incremental_outage_pct` blank.

## 6. Preserve evidence

```bash
sha256sum \
  scripts/03_3_fetch_mrdem_dtm.py \
  scripts/03_4_add_mrdem_terrain_profiles.py \
  scripts/03_5_plot_mrdem_terrain_profiles.py \
  scripts/03_6_freeze_mrdem_terrain.py \
  data/external/mrdem/MRDEM_SOURCE_RECORD.json \
  data/external/mrdem/mrdem_dtm_study_subset.tif \
  data/real/paired_fs_links_before_allocation.csv \
  data/real/terrain_review/terrain_summary.csv \
  data/real/terrain_review/terrain_profile_samples.csv.gz \
  data/real/terrain_review/terrain_profiles_review.pdf \
  data/real/terrain_review/TERRAIN_AUDIT.json \
  data/real/TERRAIN_DECISION.json \
  data/real/TERRAIN_DECISION.md \
  | tee data/real/MRDEM_TERRAIN_FREEZE.sha256

python3 scripts/14_generate_manifest.py \
  --output package_manifest_after_mrdem_terrain_freeze.sha256
```

## Stop gate

After terrain is frozen, the only remaining field-level blocker for the real S1
link table is the **explicit incremental worst-month outage allocation**. That
allocation must be set in a separate, predeclared engineering decision and must
not be selected after looking at which value makes +19 dB pass.
