# GitHub source subset

This directory is the reviewable source and build-evidence subset for the
candidate-v4.3 excluded Rorqual final campaign-worker smoke.

The wrapper corrects the superseded Nibi routing, cancels Nibi job `18953376`
if still active, deletes its temporary seed-43999 authorization token, and then
runs exactly one excluded seed-43999 final worker on Rorqual. The Nibi result is
classified as routing-correction evidence only.

The immutable locked campaign and independent-review ZIPs are already stored at
the canonical repository paths recorded in
`immutable_bindings/LOCKED_CAMPAIGN_CANONICAL_PATHS.json`; they are not
duplicated in this source subset. Their immutable NIBI-labelled filenames are
historical identifiers and do not authorize Nibi execution.

This source does not authorize seeds `44000--44029`, a Slurm array, or a merge
job. A successful Rorqual smoke advances only to building and independently
reviewing a Rorqual-native locked 30-seed package.
