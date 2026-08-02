# WSL to Rorqual workflow

The outer copy-paste block verifies the exact ZIP and basename-only SHA-256 sidecar, extracts the package, verifies both internal manifests, locates the repository, and invokes `wrappers/RUN_V45_FREEZE_TWC_HOLDOUT_FROM_WSL.sh` inside a child Bash process.

The wrapper freezes the development evidence, stages the TWC draft, pushes source without force, submits the exact fresh holdout seeds 44030--44059 to Rorqual, retrieves the return even after a scientific nonzero exit, audits it locally, pushes compact evidence, opens the Windows return folder, and prints all job and Git identifiers.

The original WSL shell remains open because the top-level block captures the child exit code and ends with `true`.
