# Integration Contract with the Existing Sionna/WMMSE Simulator

## Principle

The validated existing simulator remains the source of cellular channels, nominal beamformers, and final cellular utility. This package adds the dynamic safety layer; it does not require rewriting the baseline.

## Portable NPZ fields

Minimum bundle:

- `channels`: `[B,U,M]` or `[H,B,U,M]` for the included MISO reference evaluator;
- `nominal_beamformers`: `[B,T,M,K]` or `[H,B,T,M,K]`;
- `coupling`: `[L,B,T,M,M]` or `[H,L,B,T,M,M]`;
- `thresholds`: `[L]` or `[H,L]`, linear watts at the protected reference point;
- `tone_weights`: `[T]`;
- `noise_power`: scalar linear watts for the reference rate evaluator;
- `users_per_bs`: scalar integer;
- `metadata_json`: scalar JSON string.

Create and validate a template:

```bash
python scripts/08_export_bundle_template.py
python scripts/09_validate_experiment_bundle.py data/demo/experiment_bundle_template.npz
```

## Real integration at slot k

1. Run nominal WMMSE/learned RRM.
2. Export the physical composite precoder by sector and tone group.
3. Build/load robust incumbent coupling matrices.
4. Run the beam-space filter for a small benchmark or sector-budget/power-scale filter for the layered implementation.
5. Return the safe precoder or local budgets to the original simulator.
6. Evaluate UE rate and incumbent interference in the original simulator.
7. Save all trajectories and solver status.

## Units

- Beamformers use linear power units.
- Coupling matrices map beamformer power to watts at the protected receiver reference point.
- Threshold and coupling use the same bandwidth and reference point.
- Tone scaling is applied exactly once.
- Element gain and array factor are not double counted.
- Conducted power, TRP, and EIRP are labelled explicitly.

## Receiver limitation

The included exact rate evaluator is a small single-antenna-UE MISO reference. For multi-antenna UEs, multiple streams, or a different receiver, evaluate utility in the validated Sionna simulator after returning the safe action.

## Hybrid arrays

Apply protection to the final physical composite precoder `F_RF F_BB` or allocate certified local budgets. After factorization, recompute interference. If it exceeds a budget, back off or re-optimize; never certify the unconstrained digital target instead of the transmitted composite beam.
