# FR3 TWC Roadmap

## Phase 1 — foundation

Status: substantially complete as non-paper evidence.

- public/modelled incumbent records;
- terrain and P.452 propagation;
- EESS pass and receive-pattern geometry;
- 19-site/57-sector modelled cellular layout;
- Sionna channel/API qualification;
- exact port order and incumbent local frame;
- distributed local DLP-RZF certificate.

## Phase 2 — physical/accounting platform

Status: one-seed gate passed.

- Nibi job 18658301 completed;
- 57 sectors, 228 users, 128 ports;
- full inter-cell rate accounting;
- 587 protected samples;
- zero local budget and power-increase violations.

Boundary: not a paper result. The current proportional allocator collapses to
a common oracle scale.

## Phase 3 — controller-ready export

Status: next.

- generate all 228 users in one topology call;
- export protected-tone amplitude components;
- export local utility sufficient statistics;
- compare full topology against the chunked reference;
- retain exact fingerprints and provenance.

## Phase 4 — dynamic contribution

- static geometry-aware nonuniform allocation;
- myopic utility-aware safety;
- virtual-queue control;
- predictive/CBF safety filter;
- equal delay, update period, information and slew constraints;
- decisive rate-limit counterexample.

## Phase 5 — robustness and practicality

- uncertainty calibration;
- short- and long-term criteria;
- CSI and array error;
- message delay/drop;
- hybrid or practical array sensitivity;
- coordinator and local-BS runtime;
- bytes per update.

## Phase 6 — paper campaign

- at least 30 seeds;
- at least 5 protected passes;
- four load levels;
- global layout rotations and placement sensitivity;
- finite-network/edge sensitivity;
- confidence intervals and ablations.

## TWC go/no-go condition

Proceed to manuscript submission only when the predictive/CBF method provides
a statistically supported safety-utility advantage under identical delayed
and rate-limited conditions, with no hidden emergency slack.
