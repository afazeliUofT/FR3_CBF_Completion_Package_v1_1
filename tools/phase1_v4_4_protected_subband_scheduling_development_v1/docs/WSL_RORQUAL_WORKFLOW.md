# WSL-to-Rorqual workflow

The WSL wrapper verifies the release, activates the repository venv, runs local
syntax/tests and exact immutable-input audits, stages versioned source on
GitHub, and uploads the hash-bound package to Rorqual. Rorqual reuses the 11
preserved channels and submits a CPU array `0-10%4` with 8 CPUs, 16 GiB, and a
12-minute walltime per task; the merge uses 4 CPUs, 8 GiB, and four minutes. No
GPU, channel generation, campaign authorization token, or 30-seed rerun is
used.

The remote run key is deterministic from the package SHA, so rerunning the same
outer block reconnects to the existing run rather than submitting a duplicate.
All strict work runs in a child Bash process. The original WSL terminal returns
to its prompt after handled success or failure.
