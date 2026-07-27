# Next Immediate Step: Close the Fixed-Service S1 Adequacy Gate

## Why this is first

The fixed-service short-term cap is still provisional. Later Case-T simulations need a frozen, defensible engineering treatment. The next task is therefore not another manuscript edit. It is a real ITU-R P.530-19 wanted-link adequacy calculation on reviewed paired fixed links.

P.530 is used here only for the protected wanted fixed link. It is not used for cellular-BS-to-incumbent interference propagation; that role belongs to a validated P.452-18 implementation or independently verified export.

## Exact outcome of this step

At the end, one of the following must be documented:

1. +19 dB passes every reviewed link and the declared sensitivity tests, so it is frozen as a paper engineering cap;
2. a lower common cap is selected;
3. link-specific or multi-threshold caps are selected;
4. no short-term cap is frozen and the first paper uses only a stricter long-term treatment.

A result is never forced.

## Required input for each paired fixed link

- stable link identifier;
- TX latitude and longitude;
- RX latitude and longitude;
- TX antenna altitude above mean sea level;
- RX antenna altitude above mean sea level;
- mean terrain elevation along the wanted path, excluding trees;
- wanted-link frequency in GHz;
- documented fade margin in dB;
- explicit allocated incremental average-worst-month outage in percent;
- data provenance note;
- optional measured/approved K and dN75 overrides, otherwise official grids are mandatory.

Do not infer a fade margin from EIRP alone. A defensible fade margin comes from the wanted-link budget or a documented design value.

## Step 0 - Preserve the starting point

```bash
python scripts/14_generate_manifest.py --output package_manifest_before_work.sha256
```

Keep the original ZIP unchanged. Work in a copy or Git repository.

## Step 1 - Create and test the environment

```bash
python -m venv .venv
source .venv/bin/activate                  # Linux/macOS
# .venv\Scripts\Activate.ps1              # Windows PowerShell
python -m pip install --upgrade pip
python -m pip install -r requirements-core.txt
python -m pip install -e .
python scripts/00_validate_package.py
python -m pytest
python scripts/01_run_smoke_test.py
```

**Exit condition:** package validation and all tests pass. Demo outputs must remain under demo-labelled result folders.

## Step 2 - Obtain the official P.530 integral products

The included ITU archive is the Recommendation PDF. The numerical grids are distributed in the separate ITU components ZIP.

Online method:

```bash
python scripts/02_download_p530_products.py
```

Manual/offline method:

1. Download the English **Zip (Components)** from the official P.530-19 page.
2. Save it as `data/external/p530/P530_components.zip`.
3. Run:

```bash
python scripts/02_download_p530_products.py \
  --zip data/external/p530/P530_components.zip
```

Required outputs:

- `data/external/p530/LogK.csv`
- `data/external/p530/dN75.csv`
- latitude/longitude coordinate products if present;
- `data/external/p530/download_manifest.json`.

**Exit condition:** the product validator reports PASS and records SHA-256 hashes.

## Step 3 - Pair the real fixed links without guessing

If a reviewed database already contains a reliable pair key, use:

```bash
python scripts/03a_pair_fs_records.py \
  --input <your_raw_csv> \
  --mapping config/tafl_column_mapping.yaml \
  --output data/real/paired_fs_links_unfinished.csv
```

The script accepts only an explicit pair key. It does not pair by nearest neighbour, matching frequency alone, or antenna azimuth heuristics.

Alternatively, start from the template:

```bash
cp data/templates/paired_fs_links.csv data/real/paired_fs_links.csv
```

Replace the example row and preserve provenance.

## Step 4 - Complete terrain and altitude fields

If you have a reviewed DEM GeoTIFF and optional dependencies:

```bash
python -m pip install -r requirements-full.txt
python scripts/03b_add_dem_mean_terrain.py \
  --links data/real/paired_fs_links.csv \
  --dem <path-to-geotiff> \
  --output data/real/paired_fs_links_with_terrain.csv
```

Review all paths visually or against a trusted profile tool. The code computes an arithmetic path-sample mean excluding endpoints; it cannot decide whether the DEM or profile is suitable.

## Step 5 - Complete fade margins

Preferred: enter a reviewed `fade_margin_db` from the link budget.

Optional helper when the received level and receiver threshold are explicitly known:

```bash
python scripts/03c_compute_fade_margin.py \
  --input data/real/paired_fs_links_with_terrain.csv \
  --output data/real/paired_fs_links_ready.csv
```

The helper uses only supplied values. It does not synthesize a link budget.

## Step 6 - Declare the incremental-outage allocation

This is a project engineering decision. The code intentionally leaves it `null`.

Preferred: fill `allocated_incremental_outage_pct` per link.

Alternative: set one reviewed global value in `config/s1_adequacy.yaml`:

```yaml
allocated_incremental_outage_pct: null  # replace only after technical review
```

Create a dated decision note from `data/templates/S1_ALLOCATION_DECISION_TEMPLATE.md`.

## Step 7 - Validate the real file

```bash
python scripts/03_validate_paired_links.py \
  data/real/paired_fs_links_ready.csv \
  --mode real
```

The validator checks types, ranges, duplicate link IDs, endpoint separation, required provenance, fade margin, allocation, and P.530 calibration warnings.

## Step 8 - Run the all-candidate screen

Update `config/s1_adequacy.yaml` to point to the reviewed file, then run:

```bash
python scripts/04_run_s1_adequacy.py \
  --config config/s1_adequacy.yaml \
  --mode real
```

For each link and candidate `[10, 13, 16, 19, 23] dB`, the code reports:

- P.530-19 baseline worst-month fade exceedance;
- fade-margin penalty `10 log10(1 + 10^(I/N/10))`;
- effective fade margin;
- post-interference fade exceedance;
- incremental outage;
- allocation PASS/FAIL;
- model validity and data warnings.

## Step 9 - Perform sensitivity, not only a nominal run

At minimum sweep:

- fade margin: nominal and documented uncertainty;
- mean terrain elevation: DEM/profile uncertainty;
- K and dN75 interpolation or approved alternatives;
- incremental-outage allocation;
- candidate I/N cap.

Use:

```bash
python scripts/04b_run_s1_sensitivity.py \
  --config config/s1_adequacy.yaml \
  --mode real
```

## Step 10 - Review the evidence bundle

Inspect:

- `results/s1_adequacy/link_details.csv`
- `results/s1_adequacy/candidate_summary.csv`
- `results/s1_adequacy/incremental_outage_vs_cap.png`
- `results/s1_adequacy/audit.json`
- `results/s1_adequacy/sensitivity_summary.csv`

A candidate can pass only if:

- real mode was used;
- all intended links are present;
- official grids or documented overrides were used;
- every link meets its explicit allocation;
- unresolved validity warnings are absent;
- the result remains acceptable under the predeclared sensitivity set;
- a human reviewer confirms the data provenance and interpretation.

## Step 11 - Freeze or revise the engineering candidate

```bash
python scripts/05_freeze_s1_candidate.py \
  --candidate-db 19 \
  --reviewer "<name>" \
  --decision-note "<technical rationale>" \
  --confirm
```

The script will refuse to freeze a failed candidate or a demo run. It writes a candidate decision file; it does not silently overwrite the main YAML.

## Completion certificate for S1

S1 is closed only when the archive contains:

- the real paired-link CSV;
- pairing and source provenance;
- official P.530 products manifest;
- exact configuration;
- link-level results;
- candidate summary;
- sensitivity summary;
- audit JSON;
- figure;
- dated engineering decision stating what was frozen and what was not.
