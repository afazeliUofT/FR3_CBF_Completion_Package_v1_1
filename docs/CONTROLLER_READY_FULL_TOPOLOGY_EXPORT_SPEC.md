# Controller-ready full-topology export specification

## Motivation

Job 18658301 generated one serving sector at a time. This closed the one-seed
software/accounting gate but did not preserve cross-sector large-scale
correlation. The next single H100 job should attempt all 228 users in one
Sionna topology call.

## Required sufficient statistics

The export must provide the protected-tone decomposition

\[
A_{\mathrm{safe}}
=
A_{\perp}
+
s_{b,1}A_{b,1}
+
s_{b,2}A_{b,2},
\]

together with serving indices, other-frequency rate contributions, mode
leakages and the 587-by-57 coupling matrix. These quantities permit all first
dynamic-controller experiments to run locally without regenerating channels.

## Scientific fallback policy

A site-level or larger spatial-group fallback may be produced for diagnosis,
but it may not silently become the primary paper platform. The final record
must explicitly state whether the full 228-user topology was used.

## Validation

Every exported array requires a shape, dtype, finite-value check, SHA-256
fingerprint and an independent reconstruction test. The full-topology export
must be compared with job 18658301 to quantify the cost of sector-wise
chunking.

See `config/controller_ready_full_topology_export_v1.yaml` for exact output
names, shapes and gates.
