# Scientific status and next gate

## Source-supported result

The fresh Rorqual final worker generated the exact reference channel and
returned a seed result whose own status and exit classification were PASS. All
five candidate action traces are exact. Candidate v4.3 has zero floor, long-EESS,
and short-EESS violations; no unresolved interval; no network-wide shutdown;
strict-local scope PASS; and strict post-mode power PASS.

## Validator diagnosis

The structural validator failed because 22 candidate-only numeric fields are
not applicable to eight comparator rows. Across 40 comparator rows this creates
880 intentional blank/NaN cells. Every common numeric field is finite, and every
candidate-only numeric field is finite on the five candidate rows.

The independent smoke audit failed only one descriptive metric. The campaign
CELL_SUMMARY uses

    exp(mean(log(x + 0.001))) - 0.001,

whereas the excluded reference utility file stores

    exp(mean(log(x))).

The five discrepancies are therefore exactly the expected definition
differences (maximum 0.0007817331170665298 bit/s/Hz), not trace differences.
The preregistered primary and mandatory secondary endpoints are exact.

## Next gate

Build and review a corrected Rorqual-native locked campaign package. Do not run
confirmatory seeds in this step. After this package passes, the next major step
is one separately authorized 30-seed Rorqual campaign, followed by merged
bootstrap analysis.
