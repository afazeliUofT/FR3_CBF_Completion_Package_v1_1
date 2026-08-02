# Candidate v4.3 Rorqual campaign validator repair and review

This local-only package performs the shortest scientifically necessary next step.
It does **not** contact Rorqual or Nibi and does **not** authorize or run seeds
44000--44029.

It independently re-audits job 18132931 and proves that the final worker and
candidate hard gates passed. The legacy failure was caused by two validation
contract defects:

1. candidate-only numeric columns are intentionally blank for the eight
   comparator methods, but the old validator rejected every numeric NaN;
2. the old smoke audit directly compared an epsilon-stabilized campaign
   geometric mean with an ordinary positive geometric mean reference.

The package then builds and independently reviews a corrected Rorqual-native,
execution-locked 30-seed campaign package. Candidate-v4.3 scientific source is
unchanged. A separate authorization step is required before campaign execution.
