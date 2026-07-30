# Declared engineering envelope and sector-selective fallback

Run only:

```bash
bash RUN_DECLARED_ENVELOPE_SECTOR_BACKOFF_DROPIN.sh
```

This local-only stage takes the no-measurement branch of the array/CSI
calibration gate. It clearly declares deterministic null-depth-cap and residual
coupling-uplift scenarios, then implements a distributed sector-selective
protected-tone backoff using local constrained-PF cost curves and one scalar
coordinator price.

The stage compares the sector-selective fallback with a uniform protected-tone
backoff for long-term multiple- and single-entry designs and verifies the
paired short-term criterion. Every result receives exact per-second incumbent
safety and eligible-user floor audits.

In the exact primary one-seed screen (single-entry, 65 dB cap, 3 dB uplift),
the sector-selective method is hard-safe and floor-safe, while the uniform
backoff produces eligible-user floor violations. The selective method does use
explicit protected-tone sector mutes; their incidence is reported and must be
mapped to a practical architecture before any campaign.

This is one-seed engineering sensitivity evidence. It is not measured
calibration, practical regulatory compliance, or a paper result. The phased
multi-seed campaign remains unauthorized.
