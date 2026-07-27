# Completion Roadmap

## Phase 0 - Reproducibility gate

1. Create a clean Python 3.11 environment.
2. Run validation, tests, and smoke demos.
3. Record environment, seeds, and package hashes.
4. Keep demo and real result directories separate.

**Exit:** tests pass and no demo result is labelled as paper evidence.

## Phase 1 - Freeze or reject the fixed-service S1 engineering rule

Follow `NEXT_IMMEDIATE_STEP.md` exactly.

**Exit:** a reviewed audit freezes a defensible cap or documents why no tested common cap should be used.

## Phase 2 - Rebuild E1: static GTA fixed-service continuity

1. Use TR 38.901 UMa as the primary BS-UE model.
2. Use real GTA FS records and exact channel overlap.
3. Generate BS-incumbent coupling with a validated P.452-18 implementation or an independently verified export.
4. Do not add P.2108 clutter if the same effect is already represented in the P.452 profile calculation.
5. Run nominal WMMSE and export beamformers using the NPZ contract.
6. Reproduce the qualitative baseline: unprotected unsafe; hard null/backoff conservative; constrained WMMSE uses the budget efficiently.
7. Add static robust and safety-filter wrappers.

**Exit:** E1 is reproducible across seeds, with real provenance and no unit ambiguity. E1 is a continuity check, not the headline CBF novelty.

## Phase 3 - Build E2: dynamic aggregate stress under rate-limited RRM

1. Select a physical disturbance: traffic surge, sector activation, beam-family transition, path-gain/clutter update, or delayed actuation.
2. Define the rate limit in an operator-meaningful variable: sector leakage budget, power scale, beam/TCI transition, or hybrid analog update.
3. Build a time-indexed coupling bundle and a conservative one-step drift bound.
4. Use the same rate limit for every compared method.
5. Compare unprotected, hard backoff/null, static constrained WMMSE, static robust, myopic cap, virtual queue, and CBF.
6. Plot interference, reserve, token balance, action changes, rate, filter activity, slack, and runtime.
7. Show the required counterexample: a controller that waits at the boundary cannot recover fast enough, while the CBF acts earlier.

**Exit:** the dynamic value of the CBF is visible and statistically reproducible.

## Phase 4 - Build E3: drifting EESS earth-station geometry

1. Select a real publicly documented station or label every modelled field explicitly.
2. Archive a TLE and its retrieval time.
3. Generate the topocentric satellite track.
4. At each slot recompute station boresight, sector off-axis angle/gain, terrestrial coupling, and uncertainty set.
5. Enforce the SA.1027 long entry with a 20% exceedance budget.
6. Enforce the short entry as an always-on cap in the first paper, which is stricter than allowing 0.005% exceedance.
7. Repeat over multiple passes, satellites, traffic seeds, and uncertainty levels.

**Exit:** zero-slack certified runs meet both reported criteria over the declared experiment horizon.

## Phase 5 - Calibrate the physical uncertainty set

1. Define residuals: path loss, clutter, pointing, location, activity, antenna pattern, ephemeris, and forecast error.
2. Split calibration and evaluation data before tuning.
3. Build the set on physical parameters, not on a beam-specific scalar fitted after optimization.
4. Use split conformal or a predeclared deterministic set.
5. Report marginal and stress-stratified held-out coverage.
6. Budget risk by slowly varying uncertainty epochs, not by each short RRM slot.
7. State the evidence domain: synthetic calibration certifies only the modelled world unless measurements are added.

**Exit:** held-out coverage meets the declared level, with confidence intervals and credible stress strata.

## Phase 6 - Practical layered implementation

1. Keep the full beam-space SOCP as a small-network benchmark.
2. Implement a coordinator that computes incumbent allowances and allocates scalar sector budgets.
3. Let each BS run local WMMSE/hybrid/learned beamforming under its local budget.
4. Add active-incumbent screening and warm starts.
5. Benchmark central and layered runtime versus sectors, incumbents, tones, and antennas.
6. Report failures, slack, and control-plane overhead.

**Exit:** the paper can support a measured practicality claim. Otherwise use “O-RAN-inspired”, not “O-RAN-compliant”.

## Phase 7 - Statistical experiment campaign

For every main result:

- predeclare topology/channel/pass seeds;
- use enough independent runs for confidence intervals;
- preserve raw trajectories;
- report median/mean and dispersion as appropriate;
- report violations and emergency slack separately;
- include ablations for reserve, slew limit, uncertainty size, and active-incumbent screening;
- generate all figures from scripts.

**Exit:** every result is reproducible from archived inputs and configuration.

## Phase 8 - Final manuscript

1. Remove tutorial and audit-history prose from the paper.
2. Keep one precise novelty statement.
3. State standards/model decisions with scope and edition.
4. Include theorems with assumptions next to the claims they support.
5. Populate E1-E3 results and runtime/calibration evidence.
6. Run the readiness checker and an adversarial independent review.

**Exit:** all required checklist items pass and the archive has a SHA-256 manifest.
