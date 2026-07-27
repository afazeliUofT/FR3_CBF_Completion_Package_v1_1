# E3 Protected-Window Selection Correction v1

## Why this correction is required

The previously frozen `selected_pass_off_axis_summary.csv` was computed over
all 821 samples in the detailed track, including margins below the declared
earth-station minimum elevation of 5 degrees.  The historical sector
`E3_SITE_11_SEC_1` was selected because the satellite boresight came close to
that site while the satellite elevation was below zero degrees.

For the protected E3 case, selection must use only samples satisfying

```text
earth-station elevation >= 5 degrees
```

The corrected protected interval contains 587 one-second samples.  With the
same deterministic tie-break, the corrected site/sector is:

```text
E3_SITE_18_SEC_1
```

The historical site-11 terrain profile is not defective.  It is retained as
superseded selection evidence, but must not be used as the selected protected-
window audit path.

## What this package does

- patches future `23_2_prepare_e3_pattern_layout.py` reruns so they use the
  protected window;
- preserves the historical first-sector directory;
- writes a separate protected-window off-axis summary and correction record;
- selects `E3_SITE_18_SEC_1` deterministically;
- validates the result independently;
- stops before terrain extraction.

It does not calculate P.452 loss and does not create a paper result.

## Run

From the repository root:

```bash
source .venv/bin/activate
bash RUN_E3_PROTECTED_WINDOW_SELECTION_CORRECTION.sh
```

Required final markers:

```text
E3 PROTECTED-WINDOW OFF-AXIS REBUILD: PASS
E3 PROTECTED-WINDOW FIRST-SECTOR SELECTION: PASS
E3 PROTECTED-WINDOW SELECTION VALIDATION: PASS
E3 PROTECTED-WINDOW SELECTION CORRECTION: PASS
```

## Next terrain commands

After the correction passes:

```bash
PYTHONDONTWRITEBYTECODE=1 \
python3 scripts/03_4_add_mrdem_terrain_profiles.py \
  --links data/real/e3_first_sector_audit/first_sector_link_input.csv \
  --dem data/external/mrdem_e3_layout/mrdem_dtm_study_subset.tif \
  --output data/real/e3_first_sector_audit/first_sector_link_with_terrain.csv \
  --out-dir data/real/e3_first_sector_audit/terrain_review \
  --spacing-m 30 \
  --mean-convention inclusive \
  --expected-links 1

PYTHONDONTWRITEBYTECODE=1 \
python3 scripts/03_5_plot_mrdem_terrain_profiles.py \
  --profiles data/real/e3_first_sector_audit/terrain_review/terrain_profile_samples.csv.gz \
  --summary data/real/e3_first_sector_audit/terrain_review/terrain_summary.csv \
  --output data/real/e3_first_sector_audit/terrain_review/first_sector_profile_review.pdf
```

Review and formally disposition any QC flag before P.452 is run.
