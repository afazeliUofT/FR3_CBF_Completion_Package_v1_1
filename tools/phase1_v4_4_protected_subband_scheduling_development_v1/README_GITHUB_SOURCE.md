# GitHub source subset

This directory is the GitHub-safe, reviewable subset of the candidate-v4.4
protected-subband scheduling development package. Immutable input ZIPs are
excluded because they are already hash-bound and may be too large for routine
Git storage. Their basename-only SHA-256 sidecars are retained here. The full
standalone drop-in ZIP contains the immutable binaries and is the execution
artifact.
