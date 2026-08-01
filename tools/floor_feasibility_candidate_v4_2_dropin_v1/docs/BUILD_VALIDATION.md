# Build validation

## Executed successfully in the release environment

- Standalone handoff outer SHA-256, ZIP CRC, and 91-file internal manifest.
- GitHub branch `e3-first-sector-p452` verified identical to reviewed commit
  `76a62cda5d649cad25a6a45ccb5f0f757a99a269`; no newer work was overwritten.
- Python in-memory syntax parsing for all package Python files.
- Bash syntax checks for both wrappers.
- 16 focused unit/regression tests.
- Packaged floor, eligibility, five-pass extension, eight-method, and excluded
  seed-43999 material-failure reproduction audits.
- Original validated full-topology source-bound no-op/rate regression plus
  exact reconstruction of the real 128-port `q=0` conducted-power envelope for
  both 65/3 dB mode orientations.
- Deterministic randomized exact floor, EESS, `q=0` envelope/budget-row, and
  frozen-grid MILP versus exhaustive-enumeration checks.
- Expected remote nonzero-exit compact failure ZIP/sidecar/CRC path.
- Clean local Git source/evidence staging, normal-push, fresh-clone, and
  no-force-push simulation.
- Policy/scope scan: no executable confirmatory launch, no WMMSE, unchanged
  floor/tolerances, and hard feasibility as primary objective.
- Final ZIP CRC, internal manifests, basename-only sidecar, and forbidden
  compiled/cache artifact scan.

Machine-readable records are in `local_diagnostics/`.

## Not executable in the release environment

- The exact five-pass/eight-method candidate run against the preserved raw
  seed-43999 channel, because that channel and runtime environment are
  remote-only on Rorqual.
- A real SSH transfer, Slurm submission, or Rorqual `sacct` observation.
- The subsequent excluded H100 deployment smoke.
- Confirmatory seeds 44000--44029, which remain locked.

The immediate Rorqual job is CPU-only and reuses the preserved H100-generated
channel; it does not regenerate the channel.
