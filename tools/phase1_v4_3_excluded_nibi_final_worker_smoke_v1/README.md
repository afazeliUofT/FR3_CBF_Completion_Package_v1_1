# Candidate-v4.3 excluded Nibi final campaign-worker smoke

This package executes exactly one excluded seed (`43999`) through the final
immutable candidate-v4.3 campaign worker on one Nibi H100 node.

It does not run seeds `44000--44029`, does not submit a Slurm array or merge
job, and does not authorize the confirmatory campaign. The runtime token is
created only after all remote manifests pass, is bound to the exact locked job
package, stage `EXCLUDED_FINAL_WORKER_SMOKE_SEED43999`, and seed `[43999]`, and
is deleted after the job. It is never returned.

The smoke regenerates the seed-43999 channel on Nibi, runs five protected-pass
records and nine methods, validates the exact final worker result, and compares
its channel, comparator summaries, candidate metrics, and candidate action
traces against the frozen CPU/Rorqual-H100 reference.

Success advances only to independent review and a separate future campaign
authorization decision.
