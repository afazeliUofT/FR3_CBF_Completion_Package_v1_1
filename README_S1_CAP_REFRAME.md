# S1 cap-reframe stage

## Why this stage exists

The real 70-link nominal allocation matrix has already shown that every tested
positive always-on candidate (+10, +13, +16, +19, and +23 dB I/N) fails all
eight conditional allocation scenarios. This stage does not repeat that test or
force +19 dB to pass.

It performs the next non-circular tasks:

1. extracts every P.530 validity warning into a dedicated review table;
2. numerically brackets lower always-on I/N values on a declared 0.25 dB grid;
3. reports a separate threshold interval for every conditional scenario and for
   the intersection of all eight scenarios;
4. writes a decision record that rejects the tested positive values as
   **always-on** candidates under the tested scenario matrix;
5. leaves all link data, allocations, and regulatory YAML files unchanged.

## Critical interpretation

The screen is sensitivity evidence, not a final compliance allocation. TAFL does
not identify the operator's network portion, interference-source class, or an
exact equipment-specific mapping from the TAFL BER=1e-3 threshold event to the
G.826 quantity used in the scenario construction.

A +19 dB value may be considered later only as a separately justified rare
transient ceiling within a multi-threshold/time-budget rule. This stage does not
validate such a rule; it rejects +19 dB as an always-on cap.

## Install

Extract at the repository root and verify:

```bash
unzip -o FR3_CBF_v1_1_S1_Cap_Reframe_Hotfix.zip -d .
sha256sum -c S1_CAP_REFRAME_HOTFIX_MANIFEST.sha256
```

## Run

```bash
source .venv/bin/activate
python3 scripts/04d_run_s1_cap_reframe.py \
  --config config/s1_cap_reframe.yaml \
  2>&1 | tee logs/04d_s1_cap_reframe.log
```

The script contains no shell `exit` command and cannot close the terminal.

## First files to review

1. `results/s1_cap_reframe/model_warning_links.csv`
2. `results/s1_cap_reframe/positive_always_on_candidate_rejection.csv`
3. `results/s1_cap_reframe/scenario_threshold_intervals.csv`
4. `results/s1_cap_reframe/S1_CAP_REFRAME_DECISION.json`

Do not run the freeze script from these outputs. Resolve model warnings and
obtain an operator/administration classification before a final cap decision.
