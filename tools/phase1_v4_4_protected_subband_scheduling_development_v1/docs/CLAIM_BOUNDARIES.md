# Claim boundaries

- Eligibility, the fairness floor, floor-comparison tolerance, and long/short
  EESS verification tolerances are unchanged.
- q mode commands and RZF directions remain frozen.
- Scheduling is invoked only after the complete v4.3 deployable hierarchy fails.
- Scheduling uses physical 0.5-ms slots: 2,000 slots per second, repeated in
  every physical second of the control interval.
- Deployable coordination changes only current deficit-serving sectors and one
  fixed total set of at most four mute-only guards. Eight guards are diagnostic.
- Every stream coefficient is between zero and one, preserving the full
  post-mode total-sector and per-RF-chain conducted-power envelopes.
- Solver reserves tighten constraints; scientific acceptance is unchanged.
- Sum rate is not primary and centralized WMMSE is not used.
- The 11 channels are reused, so this is development rather than confirmation.
- Information-exchange latency, signalling, and PA/EVM remain one compact TWC
  practicality study, not hidden assumptions or compliance claims.
- No calibration or regulatory-compliance claim is made.
