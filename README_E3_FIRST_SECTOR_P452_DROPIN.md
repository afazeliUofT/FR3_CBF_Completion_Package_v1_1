# E3 Site-18 first-sector P.452 accounting drop-in

## Purpose

This drop-in runs one complete, fail-closed pipeline for the corrected protected-window audit sector `E3_SITE_18_SEC_1`:

1. validate/freeze the reviewed 78-point terrain and propagation inputs;
2. run the pinned, previously validated ITU-R P.452-18 v18.0 MATLAB implementation;
3. build external BS-gain, earth-station-gain, power, bandwidth, activity, and polarization accounting;
4. validate all identities and claim boundaries;
5. create a centralized review folder, open every review location, and produce exactly two files to upload.

This stage is deliberately labelled:

```text
ONE_SECTOR_ACCOUNTING_AUDIT_NOT_PAPER_RESULT
```

It does **not** freeze exact coast distance, a physical XPD/polarization aggregation model, final WMMSE composite beam gain, or a joint propagation/operational time-percentage rule.

## Install

Extract this ZIP from the repository root with overwrite enabled:

```bash
unzip -o FR3_CBF_v1_1_E3_First_Sector_P452_Accounting_DropIn_v1.zip -d .
sha256sum -c E3_FIRST_SECTOR_P452_DROPIN_MANIFEST.sha256
```

Every manifest entry must report `OK`.

## One command to run

Activate the repository virtual environment, then run only the master wrapper:

```bash
source .venv/bin/activate
REVIEWER_NAME="Ali Fazeli" \
  bash RUN_E3_FIRST_SECTOR_P452_DROPIN.sh --confirm-terrain-reviewed
```

The confirmation flag records that the corrected Site-18 terrain PDF was visually reviewed.

Optional overrides are available when paths differ:

```bash
MATLAB_EXE='/mnt/c/Program Files/MATLAB/R2026a/bin/matlab.exe' \
P452_WINDOWS_ROOT='/mnt/c/Users/alifa/FR3_P452_Validation_v18_R2026a' \
REVIEWER_NAME='Ali Fazeli' \
  bash RUN_E3_FIRST_SECTOR_P452_DROPIN.sh --confirm-terrain-reviewed
```

## Internal wrappers

The master invokes these automatically; do not run them separately unless diagnosing a stopped run:

```text
wrappers/e3_first_sector_p452/00_prepare.sh
wrappers/e3_first_sector_p452/10_matlab.sh
wrappers/e3_first_sector_p452/20_postprocess_validate.sh
wrappers/e3_first_sector_p452/30_package_review.sh
```

Each wrapper prints the decisive counts, assumptions, numerical ranges, and PASS/FAIL markers. The master captures each complete log and exit code. On failure, it prints the last 160 log lines and opens the failure-log folder.

## Folders opened automatically after PASS

```text
data/real/e3_first_sector_p452
results/e3_first_sector_p452_review
results/e3_first_sector_p452_review/review_upload
results/e3_first_sector_p452_review/REVIEW_INDEX.html
```

## Files to upload after the run

Upload exactly the two files printed by the master wrapper:

```text
results/e3_first_sector_p452_review/review_upload/
  E3_SITE18_FIRST_SECTOR_P452_REVIEW_BUNDLE_2026-07-26.zip
  E3_SITE18_FIRST_SECTOR_P452_REVIEW_BUNDLE_2026-07-26.zip.sha256
```

Also paste the final console output. The ZIP contains the raw accounting time series, source code, exact configuration, MATLAB audit, all validation records, figures, review index, selected logs, and an internal SHA-256 manifest.

The exact human-review list is generated at:

```text
results/e3_first_sector_p452_review/REVIEW_FILES.txt
```
