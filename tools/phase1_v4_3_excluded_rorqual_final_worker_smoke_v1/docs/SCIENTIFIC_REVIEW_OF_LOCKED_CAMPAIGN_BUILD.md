# Scientific review of the locked campaign build

## Source-supported facts

The returned local workflow passed syntax checks, ten focused tests, exact
locked-package construction, and an independent package review. The immutable
campaign package is bound to:

- package ID `77bec1efa2ea151a64481d6993399b82585eac3c1343d51adb0fc37da294e015`;
- ZIP SHA-256 `76a4aa701639a00913c5412c8ba54b86855a55ed97cb16e254ed6a7173356bd5`;
- candidate-v4.3 freeze commit `ee6708ba204c2acfe8479aeea5dd444f2cc1be04`;
- build/review commit `cc1c911ef5592a2c22834d7fb3e6550bbd4ab2ab`;
- 30 confirmatory seeds, five fixed pass records, nine methods, and 1,350
  seed/pass/method cells.

The package remains execution-locked. No cluster was contacted and no
confirmatory seed was run.

## Scientific inference

The package is ready for one excluded final-worker smoke because the frozen
candidate has already passed the CPU and Rorqual-H100 seed-43999 gates, while
the final campaign worker and fresh Rorqual channel-generation path have not yet
been exercised together. A one-seed Rorqual run is therefore the minimum
non-confirmatory integration test before any full-campaign authorization
review.

## Assumptions requiring validation

The smoke must validate exact Rorqual regeneration of the seed-43999 channel,
final-worker reproduction of the five-pass/nine-method reference result,
strict candidate hard gates, exact reference software versions, failure-safe
return packaging, and absence of any array or merge execution. The separate
information-exchange locality claim remains uncertified.
