# Return contract

Return exactly:

1. `FR3_RORQUAL_V4_3_FAILED_SEED_DIAGNOSIS_<array-job-id>.zip`
2. its basename-only `.zip.sha256` sidecar
3. `LOCAL_WSL_ORCHESTRATOR.log`

The compact return contains all eleven seed summaries, the merged decision,
interval classifications, affected-user aggregates, Slurm evidence, source
bindings, and manifests. It excludes raw channel arrays. A partial failure
return is valid evidence and must be returned rather than automatically rerun.
