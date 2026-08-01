# Claim boundaries

## Supported before the v4.3 Rorqual run

- the frozen floor, eligibility rule, variable pass extensions, and eight-method
  diagnostic are reproduced;
- v4.2 repaired all 104 original affected intervals while retaining zero EESS
  violations;
- its remaining 16 misses are numerical boundary residuals, not evidence of
  physical infeasibility;
- the strict post-mode stream comparator was feasible in all 98 v4.2 stream
  intervals, so broader `q=0` headroom is unnecessary;
- the v4.3 solver reserve tightens witness recovery without changing the exact
  floor or EESS tolerances.

## Not supported before independent review and deployment validation

- that seed 43999 has passed v4.3;
- that the controller is calibrated or regulatorily compliant;
- that fixed-RZF reweighting meets real PA, EVM, signalling, and latency limits;
- population-level or confirmatory performance;
- authorization of seeds 44000--44029.

The deployable selected action never uses a witness that is feasible only under
the broader `q=0` envelope. Global solves are diagnostic oracles, not a
centralized controller.
