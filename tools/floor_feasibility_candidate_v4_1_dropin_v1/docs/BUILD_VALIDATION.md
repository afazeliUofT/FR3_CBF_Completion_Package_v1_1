# Build validation

## Executed successfully in the release environment

- Handoff ZIP SHA-256 and internal source bindings verified.
- GitHub branch `e3-first-sector-p452` re-read through the connected GitHub
  interface and found identical to reviewed commit
  `76a62cda5d649cad25a6a45ccb5f0f757a99a269`; no newer work was overwritten.
- Python in-memory syntax parsing for all 11 Python files.
- Bash syntax checks for both wrappers.
- 13 focused unit/regression tests.
- Packaged floor, eligibility, five-pass extension, eight-method, and excluded
  seed-43999 material-failure reproduction audits.
- Original validated full-topology source-bound compatibility/no-op regression.
- Randomized exact floor linearization, EESS row, and frozen-grid MILP versus
  exhaustive-enumeration checks.
- Expected remote nonzero-exit capture and compact failure ZIP/sidecar/CRC test.
- Expected local WSL preflight failure capture and compact failure ZIP/sidecar/CRC/no-compiled-artifact test.
- Clean local Git source/evidence staging, two normal pushes, fresh-clone
  verification, and no-force-push simulation.
- Policy/scope guard scan: no executable confirmatory-seed launch, no WMMSE,
  unchanged floor/tolerances, hard feasibility primary objective.
- No `__pycache__`, `.pyc`, `.pyo`, or `.pytest_cache` artifacts retained.

## Not executable in the release environment

- The exact five-pass/eight-method candidate run against the preserved raw
  seed-43999 channel, because that channel and the reviewed runtime environment
  are remote-only on Rorqual.
- A real Slurm submission, Rorqual `sacct` observation, or SSH transfer.
- The subsequent excluded H100 deployment smoke.
- Confirmatory seeds 44000--44029, which remain locked.

The immediate Rorqual job is CPU-only and reuses the preserved H100-generated
channel; it does not regenerate the channel.
