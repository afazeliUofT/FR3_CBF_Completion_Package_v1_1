# Build validation

## Executed in the release environment

- SHA/CRC/manifest audit of the standalone handoff and both returned v4.1/v4.2
  diagnostic ZIPs;
- current GitHub branch verified at the collected-v4.2 evidence commit, four
  commits ahead of and not divergent from reviewed base
  `76a62cda5d649cad25a6a45ccb5f0f757a99a269`;
- source-bound v4.2 scientific reclassification: 104 original affected
  intervals repaired, 16 numerical boundary residuals, strict post-mode
  comparator feasible in all 98 stream-repair intervals;
- Python and Bash syntax checks;
- 18 focused tests, including solver-reserve interior certification and
  rejection of q0-only witnesses;
- packaged floor/eligibility/five-pass/eight-method audits;
- original validated full-topology no-op/rate/power regression;
- deterministic randomized floor, EESS, power-row, and grid-MILP checks;
- expected nonzero local/remote return packaging and returned-source manifest
  layout tests;
- clean two-commit Git push and stale-push rejection simulation;
- no compiled/cache artifacts;
- final ZIP CRC, internal manifests, and basename-only sidecar checks.

Machine-readable records are in `local_diagnostics/`.

## Not executable here

- the preserved-channel v4.3 run on Rorqual;
- a real SSH/Slurm/GitHub push from the packaged wrapper;
- the later excluded H100 deployment smoke;
- confirmatory seeds 44000--44029, which remain locked.
