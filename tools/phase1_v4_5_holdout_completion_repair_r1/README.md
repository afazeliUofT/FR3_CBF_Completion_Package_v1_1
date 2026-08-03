# Candidate v4.5 Fresh-Holdout Completion Repair R1

This package completes the already executed fresh holdout without adding seeds or tuning the controller.

The returned holdout contains all 30 seed archives, but only 29 complete seed results. Ten complete results were rejected by an outdated validation equation: the validator counted changed stream coefficients but omitted the schedule-mode and mutable-sector terms already included in the declared payload lower bound. Seed 44052 generated and preserved its channel, then stopped before scientific evaluation because its 7,776-mode companion-aware library exceeded a defensive enumeration guard of 4,096.

The package therefore performs exactly two non-scientific repairs:

1. validates payload as `4*changed_stream_coefficients + 4*nonzero_schedule_modes + 2*mutable_schedule_sectors`;
2. reruns only seed 44052 on its preserved channel after increasing the runtime enumeration guard to 8,192.

The frozen scientific source files, action library, objective, hard floor, EESS constraints, tolerances, fixed-RZF directions, and bounded action policy are unchanged. No GPU, new channel, new seed, or automatic extra probe is authorized.

On completion it merges all 30 seed clusters, computes the preregistered 10,000-resample seed-cluster bootstrap, writes the paper-facing holdout table, pushes compact evidence to GitHub, and returns one ZIP plus sidecar. The next gate is manuscript finalization, not another simulation campaign.
