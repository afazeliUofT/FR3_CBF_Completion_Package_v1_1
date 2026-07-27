# Next Immediate Step

## Gate

Frozen 57-sector Sionna 2.0.1 DLP-RZF pilot.

## Qualified foundation

- Clean `sionna-no-rt==2.0.1` candidate.
- `torch==2.9.1`.
- CPU UMa and UMi API qualification passed.
- UMa model-consistent BS height: 25 m.
- UMi model-consistent BS height: 10 m.
- Distributed local RZF plus exact local leakage projection.
- No network-wide UE CSI or joint precoder.

## Required sequence

1. Map the exact experiment parameters to ETSI TR 138 901 V19.4.0.
2. Adapt the frozen 19-site/57-sector IDs and geometry to the Sionna topology.
3. Generate one reproducible UMa seed with four users per sector.
4. Compute local RZF from local UE CSI only.
5. Include all inter-cell UE interference in SINR/rate metrics.
6. Reconstruct transmit power and rates independently from exported tensors.
7. Apply and verify DLP-RZF local leakage constraints.
8. Measure CPU/GPU memory and runtime.
9. Preserve the pilot as non-paper evidence before scaling.

## Stop condition

Do not launch the final campaign until the topology mapping, channel version
mapping, inter-cell rate reconstruction, leakage verification, and one-seed
GPU pilot all pass.
