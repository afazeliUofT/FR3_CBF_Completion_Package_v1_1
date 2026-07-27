# Next Immediate Step

## Gate

Standards-aligned 57-sector local-channel and distributed IA-RZF experiment.

## Frozen architecture

- Each BS uses only local UE CSI.
- Nominal local beamforming is RZF or a standards-compatible hybrid/codebook
  implementation.
- A closed-form local projection enforces one scalar incumbent-leakage budget.
- The slow layer exchanges scalar leakage/utility telemetry and scalar budgets,
  never UE channel vectors or complex precoders.
- Nonnegative local budgets sum to the aggregate protected-receiver allowance.

## Required sequence

1. Freeze a standards-aligned local channel/user model and exact software
   versions.
2. Generate local nominal RZF beams for the frozen 57 sectors.
3. Independently reconstruct local rates and transmit powers.
4. Apply the certified local leakage projection.
5. Implement static, myopic, queue-based, and predictive/CBF budget schedules
   with identical update periods, delays, and information.
6. Include realistic activity/load cases rather than only all-sector full load.
7. Re-verify the actual hybrid/codebook composite precoder when used.
8. Repeat across passes, user seeds, load levels, and uncertainty epochs.

## Stop condition

Do not call E3 paper-grade until actual local channels, composite beams, UE
rates, loading, rate-limited budget actions, zero-slack safety, runtime, and
statistical repetitions are all present.
