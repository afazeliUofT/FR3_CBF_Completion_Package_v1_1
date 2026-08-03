# Candidate-v4.5 holdout completion R2

This standalone package completes **only holdout seed 44052** after the R1
CPU job reached its 12-minute Slurm wall-time. It does not create a new seed,
regenerate the preserved channel, request a GPU, alter candidate-v4.5, change
any floor/EESS constraint, or authorize additional tuning.

The five protected-pass evaluations are scientifically independent. R2 runs
those exact evaluations as a five-task CPU array and assembles them into the
same canonical seed result before running the repaired structural validator and
the frozen 30-seed merge/bootstrap.

Resource request:

- pass array: `0-4%5`, 8 CPUs, 4 GiB, `00:20:00` per pass;
- assembly/merge: 4 CPUs, 4 GiB, `00:05:00`;
- GPU: none;
- channel generation: none.

See `docs/SCIENTIFIC_STATUS_AND_NEXT_GATE.md` and
`docs/WSL_RORQUAL_WORKFLOW.md`.
