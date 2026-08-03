# Wall-time and stopping policy

The fresh-holdout H100 workers that reached scientific evaluation completed in approximately 2:44--5:35 with 16 GiB requested memory and roughly 2.0--2.3 GiB observed host RSS. Seed 44052 stopped after 47 seconds at the mode-count guard, after its channel had already been generated.

The completion job reuses that preserved channel, requests no GPU, and evaluates the already-declared 7,776-mode library. Its 12-minute, 8-CPU, 16-GiB request is a bounded upper limit: slightly more than twice the longest measured full worker runtime, with margin for the larger mode library. The merge requests 5 minutes, 4 CPUs, and 8 GiB.

No new seed, channel generation, controller tuning, or automatic follow-on probe is authorized. Once the completed 30-seed merge is produced, the simulation campaign stops and work proceeds to the 13-page TWC manuscript and one compact practicality/limitations section using existing runtime, action-sparsity, coordination-scope, and payload data.
