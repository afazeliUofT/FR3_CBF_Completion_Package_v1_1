# FR3 CBF Standalone Completion Package v1.1

## Project

**Certified Dynamic Interference-Safety Filters for Incumbent-Protected FR3 Spectrum Sharing**

This directory is the new working home for the project. It contains the canonical system model, a plain-language tutorial, the exact completion sequence, a standards-aware YAML file, executable reference code, strict real-data gates, tests, and the user-supplied official ITU-R P.530-19 archive.

You do not need to reconstruct the project from earlier conversations.

## Current status

The following parts are mature enough to implement:

- the research question and defensible novelty boundary;
- the beam-space incumbent-interference model;
- robust uncertainty sets defined on physical parameters;
- rate-limited RRM and the discrete-time safety-filter logic;
- an exact sample-path exceedance budget for time-percentage criteria;
- an EMA barrier used only as a reserve-margin governor;
- a fully digital benchmark filter and a practical sector-budget/power-scale implementation;
- a harmonized channel-model stack and an auditable standards YAML;
- the experiment plan: E1 static fixed service, E2 dynamic fixed service, and E3 drifting earth-station geometry.

The following evidence is still missing and must be produced before submission:

- a reviewed real paired GTA fixed-link file;
- a justified incremental-outage allocation for the S1 gate;
- the final decision on the provisional +19 dB short-term engineering cap;
- validated P.452-18/P.2108 coupling for the cellular-to-incumbent paths;
- a real export from the existing Sionna/WMMSE simulator;
- held-out uncertainty-set coverage results;
- runtime and scalability results;
- final E1-E3 figures, tables, confidence intervals, and a populated paper results section.

## Read these files in this order

1. `docs/FR3_CBF_Tutorial.pdf`
2. `docs/FR3_CBF_System_Model.pdf`
3. `docs/FR3_CBF_Completion_Execution_Guide.pdf`
4. `NEXT_IMMEDIATE_STEP.md`
5. `COMPLETION_ROADMAP.md`
6. `config/regulatory_constants.yaml`
7. `DATA_REQUIREMENTS.md`
8. `INTEGRATION_CONTRACT.md`
9. `PAPER_COMPLETION_CHECKLIST.md`

Editable sources for all three PDFs are in `docs/source/`.

## Exact next action

The next scientific gate is **S1 fixed-link adequacy**. The +19 dB short-term fixed-service cap is still a provisional paper engineering candidate. It must not be called a regulatory requirement and must not be frozen from synthetic data.

The quickest tested setup is `./RUN_FIRST.sh` on Linux/WSL/macOS or
`./RUN_FIRST.ps1` in Windows PowerShell. The equivalent commands are:

```bash
python -m venv .venv
source .venv/bin/activate                 # Linux/macOS
# .venv\Scripts\Activate.ps1             # Windows PowerShell
python -m pip install --upgrade pip
python -m pip install -r requirements-core.txt
python -m pip install -e . --no-build-isolation
python scripts/00_validate_package.py
python -m pytest
python scripts/01_run_smoke_test.py
```

For the existing validated TensorFlow/Sionna environment, do not let pip replace its
dependencies. Install only this local package:

```bash
python -m pip install -e . --no-build-isolation --no-deps
```

Then obtain the P.530-19 integral digital products:

```bash
python scripts/02_download_p530_products.py
```

The user-supplied `source_documents/R-REC-P.530-19-202509.zip` contains the official Recommendation PDF. The `LogK.csv` and `dN75.csv` integral products are a separate ITU components download. The downloader records hashes and refuses to pretend that the PDF archive contains those grids.

Next, create the real paired-link file:

```bash
cp data/templates/paired_fs_links.csv data/real/paired_fs_links.csv
# Replace the example row with real reviewed links.
python scripts/03_validate_paired_links.py data/real/paired_fs_links.csv --mode real
```

Set an explicit per-link or project-level incremental worst-month outage allocation in `config/s1_adequacy.yaml`, then run:

```bash
python scripts/04_run_s1_adequacy.py --config config/s1_adequacy.yaml --mode real
```

Review:

- `results/s1_adequacy/link_details.csv`
- `results/s1_adequacy/candidate_summary.csv`
- `results/s1_adequacy/incremental_outage_vs_cap.png`
- `results/s1_adequacy/audit.json`

Only after an all-link technical review may a candidate be frozen:

```bash
python scripts/05_freeze_s1_candidate.py \
  --candidate-db 19 \
  --reviewer "<name>" \
  --decision-note "<why the allocation and sensitivity are acceptable>" \
  --confirm
```

A freeze is a project engineering decision, not a new rule.

## Main experiment sequence after S1

```bash
python scripts/08_export_bundle_template.py
python scripts/09_validate_experiment_bundle.py data/demo/experiment_bundle_template.npz
python scripts/10_run_e1_static_fs.py --config config/e1_static_fs.yaml
python scripts/11_run_e2_dynamic_fs.py --config config/e2_dynamic_fs.yaml
python scripts/12_run_e3_tracking_eess.py --config config/e3_tracking_eess.yaml
python scripts/07_run_calibration.py --config config/calibration.yaml
python scripts/15_check_submission_readiness.py
```

The included E1-E3 default runs are labelled **DEMO**. They test software and the qualitative control mechanism; they are not paper evidence. Real paper runs require the real data and coupling bundle described in `DATA_REQUIREMENTS.md` and `INTEGRATION_CONTRACT.md`.

## Evidence levels

1. **Demo** - synthetic code-path check; never paper evidence.
2. **Validated model run** - official model versions, real incumbent records, documented model decisions, calibrated uncertainty, and reproducible code; supports claims only inside the modelled world.
3. **Physical evidence** - operator or field measurements; required for claims that uncertainty coverage transfers to the physical network.

## Claims this package deliberately prevents

- CBFs themselves are new.
- A fixed per-slot risk gives an infinite-horizon probability guarantee.
- Synthetic calibration certifies the physical world.
- An EMA alone proves a time-percentage rule.
- +19 dB is an in-force 7-8 GHz fixed-service rule.
- P.530 is the cellular-to-incumbent interference model.
- A full central SOCP is near-real-time deployable without measured runtime.
- A fully digital solution is directly implementable on a hybrid array without factorization and re-verification.
