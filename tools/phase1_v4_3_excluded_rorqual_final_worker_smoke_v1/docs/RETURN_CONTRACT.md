# Return contract

Return exactly:

1. `FR3_RORQUAL_V4_3_FINAL_WORKER_SMOKE_43999_<job-id>.zip`, or the generated
   diagnostic/emergency ZIP on failure;
2. its matching basename-only `.zip.sha256` sidecar;
3. `LOCAL_WSL_ORCHESTRATOR.log`.

Also retain `SUPERSEDED_NIBI_CANCELLATION.log` in the opened return folder.

Do not rerun automatically after a nonzero result and do not run seeds
`44000--44029`.
