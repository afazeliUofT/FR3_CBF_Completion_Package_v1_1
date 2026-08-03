# Scientific status and next gate

## Source-supported R1 facts

- Seed job `18207112` ended `TIMEOUT` after `00:12:04`.
- Batch MaxRSS was `764704K`; memory was not limiting.
- No completed seed-44052 result was produced.
- The preserved channel and original 29 completed holdout seeds remain valid.
- The 29-seed provisional primary effect remains positive, but it is not the
  final paper result.

## Scientific inference

The five pass evaluations have no cross-pass state propagation. Each invokes
the same frozen calculation from the same full-load nominal moving-average
initialization. Splitting passes changes orchestration only.

## Exact next gate

Run only seed 44052 as five independent pass jobs, assemble the five outputs,
validate the canonical seed result, and merge all 30 holdout seeds. No further
seed or controller variant is authorized.

After a valid 30-seed merge, simulation development stops and the next gate is
completion of the 13-page TWC manuscript plus one compact practicality section.
