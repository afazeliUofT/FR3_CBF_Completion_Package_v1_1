<!-- BEGIN VALIDATED FULL-TOPOLOGY EXPORT -->
## Validated controller-ready full-topology export

- Source H100 job: `18696267`
- Corrected CPU validation job: `18704028`
- Full topology: 228 users, 57 sectors, 128 ports, 9 frequencies
- Full response shape: `[228,57,128,9]`
- V4 validation: `PASS`
- Legacy job-18658301 reproduction: bitwise channel hash match
- Minimum total-band common-scale retention: `99.296767%`
- Minimum protected-band common-scale retention: `93.018752%`
- Claim boundary: `CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_ONE_SEED_NOT_PAPER_RESULT`

The full-versus-chunked network sum differs by only about 0.15%, but the
per-user nominal-rate correlation is only about 0.293. This confirms that the
full topology is necessary for user-level controller evaluation.

The exported pass contains a natural delay/slew safety trap, but no practical
predictive controller has yet been demonstrated.

**Next gate:** `IMPLEMENT_LOCAL_STATIC_MYOPIC_AND_PREDICTIVE_CONTROLLERS`
<!-- END VALIDATED FULL-TOPOLOGY EXPORT -->

# Current Project Status

## Status date

2026-07-29

## Status in one sentence

The propagation, incumbent, topology, standards-subset, exact steering, and
distributed DLP-RZF foundations are complete as non-paper evidence. Nibi job
18658301 successfully closed the one-seed 57-sector, 228-user software and
physical-accounting gate with zero local budget violations and zero projection
power-increase violations. The dynamic delayed/rate-limited controller and
paper-grade statistical campaign remain open.

## Frozen successful gate

- Job: `18658301`
- GPU: NVIDIA H100 80 GB HBM3
- Sectors/users: 57 / 228
- Users per sector: 4
- BS ports: 128
- Frequency samples: 9
- Protected-pass samples: 587
- Minimum network sum-rate retention: `99.149152%`
- Claim boundary: `ONE_SEED_SOFTWARE_AND_PHYSICAL_ACCOUNTING_GATE_NOT_PAPER_RESULT`

## Current gate

`INDEPENDENT_REVIEW_THEN_PREPARE_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT`

## Immediate requirements

1. Review and merge the frozen job-18658301 evidence and provenance overlay.
2. Freeze the delayed/rate-limited dynamic experiment contract.
3. Prepare one controller-ready full-228-user topology export.
4. Compare the full-topology export with the four-user-chunk reference.
5. Implement practical static, myopic, virtual-queue, and predictive/CBF
   controllers locally before launching a multi-seed campaign.

## Open paper gates

- exact long-term incumbent criterion;
- uncertainty calibration;
- practical array/hybrid sensitivity;
- full-topology spatial correlation;
- rate-limit counterexample;
- controller runtime and message overhead;
- multi-seed, multi-pass confidence intervals.
