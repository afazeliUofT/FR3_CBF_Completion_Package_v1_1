# E3 earth-station pattern and cellular-layout freeze

This stage closes the next gate after the E3 reference intake. It does **not**
generate cellular-to-incumbent P.452 coupling yet.

## Scientific choices

- The 13 m public dish diameter and public station identity are retained.
- The actual measured receive pattern and aperture efficiency are unavailable.
- ITU-R SA.509-3 is therefore used as an explicit **reference model**, not as a
  claim that it is an EESS-specific mandatory pattern.
- Section 1.2 (multiple-entry pattern) is the nominal aggregate-interference
  model for 57 sectors. Section 1.1 is retained as a conservative single-entry
  sensitivity.
- The nominal aperture efficiency 0.65 and grid 0.55/0.65/0.75 are declared
  model decisions, not measurements.
- The 19-site/57-sector UMa layout is deterministic and modelled. It is not an
  operator deployment. The baseline cluster centre is 3 km south of the
  reference station, giving a 2 km nearest-site distance. A predeclared
  placement/height sensitivity grid is written for later experiments.

## First run

```bash
bash RUN_E3_PATTERN_LAYOUT_PREPARE.sh
```

Then review:

- `data/real/e3_pattern_layout_review/earth_station_pattern_review.png`
- `data/real/e3_pattern_layout_review/e3_layout_review.png`
- `data/real/e3_pattern_layout_review/e3_layout.geojson`
- `data/real/e3_pattern_layout_review/bs_sites_review.csv`
- `data/real/e3_pattern_layout_review/selected_pass_off_axis_summary.csv`
- `data/real/e3_pattern_layout_review/E3_PATTERN_LAYOUT_REVIEW_CHECKLIST.md`

Do not set confirmations to true without actual review.

## Freeze

Edit only the booleans under `manual_confirmations` in
`config/e3_pattern_layout.yaml`. Then run:

```bash
python3 scripts/23_2_prepare_e3_pattern_layout.py \
  --config config/e3_pattern_layout.yaml \
  --confirm
```

The next gate is one audited cellular-sector-to-earth-station P.452 path.
