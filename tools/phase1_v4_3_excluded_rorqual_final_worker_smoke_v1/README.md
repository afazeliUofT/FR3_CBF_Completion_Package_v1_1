# Candidate-v4.3 excluded Rorqual final campaign-worker smoke

This package corrects the execution-site routing error in the superseded Nibi
smoke. The returned output showed Nibi job `18953376` pending for priority. The
wrapper first cancels that job if it is still active and deletes its ephemeral
seed-43999 authorization token. That Nibi run is treated
as routing-correction evidence only, never as confirmatory scientific evidence.

The package then executes exactly one excluded seed (`43999`) through the
unchanged immutable candidate-v4.3 campaign worker on one Rorqual H100 node.
It generates the channel afresh on Rorqual with user/channel seeds
`87998/87999`, runs five protected-pass records and all nine frozen methods,
and compares the generated channel and scientific traces against the frozen
CPU/Rorqual-H100 reference.

The embedded locked campaign ZIP retains `NIBI` in its filename and native
authorization string because those are immutable historical identifiers. Its
scientific worker and inputs are not changed. This wrapper supplies a separate,
hash-bound Rorqual execution contract and does not use the locked Nibi campaign
submission scripts.

The package never runs seeds `44000--44029`, never submits a Slurm array or
merge job, and never authorizes the full campaign. A successful smoke advances
only to building and independently reviewing a Rorqual-native locked 30-seed
campaign package.
