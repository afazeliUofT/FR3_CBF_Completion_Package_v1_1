# Return contract

Return exactly:

1. `FR3_NIBI_V4_3_FINAL_WORKER_SMOKE_43999_<job-id>.zip`, or the generated
   diagnostic/emergency ZIP if the scientific or infrastructure gate fails;
2. its matching basename-only `.zip.sha256` sidecar;
3. `LOCAL_WSL_ORCHESTRATOR.log`.

The return excludes both the authorization token and the raw approximately
119.8-MB frequency-response array. It includes the channel record and hashes,
all compact final-worker result traces, the independent scientific audit,
exact software environment, Slurm accounting, authorization record without
token contents, and immutable source/contract bindings.

Do not rerun automatically after a nonzero result. Do not run seeds
`44000--44029` after this smoke.
