# P.452 Pilot TAFL-Role Hotfix

## Confirmed defect

The pilot preparation script checked the canonical TAFL endpoint-role field for
`T` and `R`.  The frozen ISED TAFL Fixed Service source used by this project
stores the values as `TX` and `RX`, as already enforced by the detailed pairing
and allocation-evidence stages.

The defect caused:

```text
ValueError: Resolved TAFL records do not have expected T/R roles
```

## Repair

The replacement script:

- requires the canonical values `TX` and `RX`;
- rejects shortened or reversed role values;
- reports the resolved IDs and observed role values on failure;
- records `canonical_tafl_tx_role` and `canonical_tafl_rx_role` in the frozen
  pilot-parameter JSON;
- changes no scientific input, pairing, terrain, P.530, P.452, or regulatory
  evidence.

The hotfix contains no `.pyc`, `.pyo`, or `__pycache__` artifacts.
