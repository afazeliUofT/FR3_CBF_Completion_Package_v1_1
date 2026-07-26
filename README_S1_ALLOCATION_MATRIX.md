# S1 Allocation-Matrix Hotfix

## Why this stage exists

The frozen TAFL evidence confirms 70 digital point-to-point links and complete
capacity/bandwidth metadata, but TAFL does not identify whether each link is an
access, short-haul, long-haul, or international path element. It also does not
establish whether the future IMT sharing case is legally co-primary or belongs
to the "other-source" category. Therefore, selecting one universal outage
allocation would be an unsupported assumption.

This hotfix does two things without choosing a final allocation:

1. builds conditional ITU-R F.1565-1/G.826 SESR scenarios; and
2. computes the allocation-free P.530 required-allocation envelope for each
   candidate I/N cap.

## Standards logic represented in the configuration

- ITU-R F.1094-2 apportions performance degradation as X=89% for the fixed
  service, Y=10% for co-primary interservice sharing, and Z=1% for other
  interference sources.
- ITU-R F.1565-1 incorporates Y=10% in its co-primary tables.
- For national access and short-haul G.826 links, F.1565 gives
  SESR degradation = 0.0002*B or 0.0002*C, with provisional B/C in
  [0.075, 0.085].
- For national long-haul G.826 links, F.1565 gives SESR = 0.0002*A,
  with A determined from A1 and link length.
- F.1565 states that other-source Z=1% values are obtained by dividing the
  co-primary values by ten.
- F.1703 states that partitioning availability objectives among causes is
  outside its scope and that multi-hop allocation is an operator responsibility.

## Evidence boundary

The project presently uses P.530 average-worst-month exceedance of the TAFL
BER=1e-3 receiver threshold as a screening proxy for SESR degradation. This is
a model decision, not a universal equipment-specific equivalence. The scenario
files must not be described as final compliance allocations.

## Commands

```bash
python3 scripts/03_8_build_s1_allocation_scenarios.py \
  --config config/s1_allocation_matrix.yaml

python3 scripts/04c_run_s1_allocation_matrix.py \
  --config config/s1_allocation_matrix.yaml
```

Review:

```text
results/s1_allocation_matrix/required_allocation_envelope.csv
results/s1_allocation_matrix/scenario_candidate_summary.csv
results/s1_allocation_matrix/scenario_pass_matrix.csv
results/s1_allocation_matrix/required_allocation_envelope.png
results/s1_allocation_matrix/audit.json
```

## Decision after the nominal matrix

- If a candidate fails every conditional scenario, reject it before sensitivity.
- If a candidate passes even the strict long-haul/other-source scenario, it is
  robust to the tested classification range, but still requires full model
  sensitivity and human review.
- If the decision changes with network portion or source class, obtain an
  operator/administration classification before freezing anything.
- Only candidates that remain relevant after this matrix should enter the full
  81-case P.530 parameter sensitivity campaign.
