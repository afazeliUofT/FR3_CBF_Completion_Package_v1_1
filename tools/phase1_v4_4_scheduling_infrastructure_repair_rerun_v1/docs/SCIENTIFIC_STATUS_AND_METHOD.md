# Scientific status and method

## Source-supported failure diagnosis

Array job 18153316 produced a valid compact return for all eleven target seeds.
Each worker wrote `CELL_SUMMARY.csv` and all five method/action trace archives,
then raised:

`TypeError: Object of type ndarray is not JSON serializable`

at the write of `PASS_AUDITS.json`. The merge correctly refused to construct a
scientific summary because all eleven `V44_SCHEDULING_SEED_RESULT.json` files
were absent.

## Preliminary salvage audit

The completed cell summaries are internally coherent and all eight frozen
comparators reproduce the original campaign exactly. They provide preliminary,
not final, evidence that v4.4:

- preserves zero long- and short-term EESS violations;
- preserves strict-local and strict post-mode power gates;
- reduces v4.3 floor-violation user-seconds from 19,994 to 6,540;
- reduces unresolved intervals from 1,736 to 523;
- closes four of the eleven failed development seeds.

These values are not frozen paper evidence because comparator checking,
`PASS_AUDITS.json`, seed summaries, the merge, and final return verification did
not complete.

## Repair

The replay JSON writer now converts NumPy arrays to lists and NumPy scalars to
native Python scalars. The candidate-v4.4 scientific modules remain unchanged.

## Decision after rerun

- If all eleven seeds pass, freeze v4.4 and begin the TWC draft while a fresh
  holdout and one compact practicality study run in parallel.
- If the validated result confirms residual failures, use the merged
  interval/seed summaries to design one targeted scheduling refinement. Do not
  repeat the 30-seed campaign or weaken the floor.
