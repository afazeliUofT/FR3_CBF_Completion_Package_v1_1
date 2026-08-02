# Return contract

Return exactly:

1. `FR3_RORQUAL_V4_3_R2_30SEED_CAMPAIGN_<array-job-id>.zip`;
2. its basename-only `.zip.sha256` sidecar;
3. `LOCAL_WSL_ORCHESTRATOR.log`.

The campaign ZIP contains all 30 compact seed returns, merged summaries, bootstrap outputs, hash indexes, Slurm evidence, and immutable bindings. It excludes raw frequency-response arrays and the authorization token.
