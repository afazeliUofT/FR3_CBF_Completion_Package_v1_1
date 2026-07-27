# E3 one-sector review and all-site terrain drop-in

Run only the master wrapper:

```bash
bash RUN_E3_ONE_SECTOR_REVIEW_AND_ALL_SITE_TERRAIN_DROPIN.sh
```

It performs an independent full-row review of the validated Site-18 accounting
audit, generates required gain/backoff envelopes, creates precisely named
global and nominal accounting-component files, prepares one terrain profile
for each of the 19 unique modelled sites, validates/classifies terrain flags,
pushes all review evidence to the existing GitHub branch, prints every required
outcome, and opens the folders/PDF required for review.

It does not run all-site P.452 and does not create a paper result.

The GitHub evidence also includes an uncompressed all-profile sample table and per-site adjacent-step/slope QC metrics so the next review does not depend on decoding a gzip file.
