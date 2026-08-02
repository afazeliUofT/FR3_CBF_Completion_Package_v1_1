# Wall-time and resource policy

The completed 30-seed H100 workers ran in 2:42--3:00, with host MaxRSS below
2.4 GiB. The inherited 4:00:00 / 124 GiB request was a legacy conservative
contract and was not a fair evidence-based request after the smoke timings were
known. It can reduce backfill opportunities and increase queue latency.

Future repeated campaign workers should use 00:10:00 and 16 GiB unless a new
measured workload justifies more. This diagnostic is heavier because it solves
several additional LP action classes on every unresolved interval; it therefore
uses a still-bounded 00:15:00, 8 CPUs, and 16 GiB. The merge uses 00:05:00,
4 CPUs, and 8 GiB. No GPU is requested and no channel is regenerated.
