# Controller-ready full-topology export

This package is a single-seed, non-paper export gate.

It attempts one Sionna topology call with all 228 users and all 57 sectors,
exports the full frequency response and compact controller sufficient
statistics, reproduces the legacy job-18658301 chunked platform numerically,
and compares the two generation modes.

The package does not implement the delayed/rate-limited controllers. It creates
the local data platform required to implement and test them without repeatedly
regenerating Sionna channels.
