# FR3 TWC v4.5 — Reviewer-Mandatory Revision Package

## Purpose

This package addresses the independent review in `reviewer_feedback/07_VERDICT_FILLED.md` without changing the controller, adding seeds, or rerunning the scientific campaigns. It contains:

- the revised 13-page IEEE TWC candidate PDF and LaTeX source;
- an item-by-item independent evaluation of the review;
- a response-to-reviewer document;
- a closure matrix for the seven mandatory items;
- reproducible audits for the array metadata, SA.1027 thresholds, SA.509 scope and sensitivity, TR 38.901 claim scope, P.452 validation, and utility interpretation;
- corrected metadata files kept separate from the immutable executed campaign inputs;
- the compact final-holdout evidence required to regenerate the new SA.509 frozen-action sensitivity;
- a local-only WSL wrapper that compiles, audits, stages, and pushes the revision without contacting a cluster.

## Recommended reading order

1. `01_SCIENTIFIC_EVALUATION_OF_REVIEWER_FEEDBACK.md`
2. `02_RESPONSE_TO_REVIEWER.md`
3. `manuscript/FR3_TWC_v4_5_reviewer_mandatory_revision_candidate_v3.pdf`
4. `03_MANDATORY_REVISION_CLOSURE_MATRIX.csv`
5. `04_CLAIM_CHANGES.md`
6. `audits/MANDATORY_REVISION_EVIDENCE_AUDIT.json`
7. The individual audit JSON files under `audits/`

## Scientific status

The reviewer found no fundamental mathematical, statistical, or model-implementation error. That conclusion is supported. The seven mandatory items are provenance, scoping, and metadata-consistency repairs. Three reviewer formulations are narrowed in this package:

1. the study was Git-frozen and pre-specified before holdout execution, but not formally registered in an external preregistration registry;
2. treating the aggregate cellular network as one SA.1027 sharing entry is an explicit conservative study convention, not a normative statement derived from SA.1023;
3. the SA.509 single-entry curve is a conservative reference-pattern stress, not a certified bound for the actual EESS station because no measured station pattern is available.

## No new simulation decision

No new channel seed, controller optimization, or cluster computation is required. The only new numerical result is a deterministic post-processing sensitivity: the SA.509 single-entry curve is exactly 3 dB above the multiple-entry curve throughout the protected off-axis window, so the archived frozen candidate EESS ratios can be re-evaluated exactly by a factor of two. This is explicitly reported as a frozen-action stress, not a reoptimized alternative scenario.

## Integrity checks

From the extracted package root:

```bash
python3 scripts/verify_package.py --package-root .
bash scripts/run_local_review_audit.sh .
```

The second command requires Python, NumPy, pandas, `latexmk`, `pdfinfo`, and `pdftotext`. It contacts no cluster.
