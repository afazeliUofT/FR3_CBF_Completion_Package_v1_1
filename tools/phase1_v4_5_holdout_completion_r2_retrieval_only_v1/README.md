# Candidate v4.5 holdout-completion R2 retrieval-only recovery

The five seed-44052 pass jobs and the assembly/30-seed merge already completed on Rorqual. The remote wrapper created the final return ZIP successfully. The previous WSL run failed only during the final `scp` connection after MFA.

This package performs no scientific computation. It uses one SSH session to verify and stream the existing remote ZIP and sidecar, verifies the local ZIP/manifest, independently audits the final 30-seed result, stages compact evidence and the paper-facing holdout table on GitHub, and opens the Windows return folder.

It does not submit Slurm jobs, regenerate channels, execute seeds, request a GPU, change the controller, or authorize further algorithm tuning.
