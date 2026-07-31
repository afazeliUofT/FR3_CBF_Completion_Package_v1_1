# Immutable phase-1 Nibi job-package design

The package is a non-executable review artifact. It is bound to candidate-v3
commit and ZIP SHA-256 and to the external round-2 PASS record.

## Compute DAG

1. Thirty H100 array tasks correspond one-to-one with campaign seeds
   44000--44029.
2. Each task generates one full 228-user/57-sector/128-port cellular channel
   realization. The deterministic mapping is `user_seed=2s` and
   `channel_seed=2s+1`.
3. The task maps that one channel to the generic 64-RF-chain architecture once,
   caches the required load states, and reuses the channel and architecture
   across all five fixed protected-pass records and all eight methods.
4. Each task validates its five-pass, eight-method result and writes a compact
   result bundle plus a persistent channel bundle on Nibi scratch.
5. A separate CPU merge/finalization stage validates all 30 seed bundles,
   computes the preregistered seed-cluster bootstrap, and builds the final
   compact review return.

No submission command is active. Array and merge launchers return exit code 64
until the immutable package receives independent PASS and a separate execution
authorization token.

## Primary endpoint

The primary endpoint is the final moving-average sum-log utility. The
duration-weighted mean moving-PF utility is mandatory secondary reporting.

## Method fairness

The reactive-myopic comparator has current coupling information only and no
future envelope. It receives the same sector-selective emergency fallback as
the predictive method. Unshielded myopic and virtual-queue methods remain
negative controls. The instantaneous common-scale method is explicitly
noncausal.

## Reviewed channel-generator source binding

The channel-generator code and inputs are extracted at build time from the
committed full-topology source bundle with SHA-256
`206c8cc7aa18c3616f70fba6c56b72af8a76267b59f9f446baa019dede0085b5`.
The builder verifies its internal manifest, the original one-seed review/input/
return lineage hashes, and 15 exact input-file hashes. The job package includes
the original source metadata and manifest plus a machine-readable binding
record. This removes dependence on an untracked working-tree input directory.
