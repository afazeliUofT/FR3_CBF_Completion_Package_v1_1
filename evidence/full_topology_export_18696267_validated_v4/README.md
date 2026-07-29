# Validated full-topology export: jobs 18696267 and 18704028

Status: `PASS_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_ONE_SEED`

The source H100 job generated the complete 228-user full-topology export and
then exited because its original validator was superseded. CPU validation job
18704028 independently passed the source-linked V4 validation.

Strong accepted facts:

- one Sionna topology call with 228 users and 57 sectors;
- response shape `[228,57,128,9]`;
- full raw channel/precoder/amplitude linkage validated;
- legacy job-18658301 chunked reference reproduced bitwise;
- protected decomposition, mode leakage, incumbent aggregation, SINR and rate
  chains validated;
- controller-ready full channel is retained locally.

Boundary:

`CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_ONE_SEED_NOT_PAPER_RESULT`

The result is a controller platform, not a TWC paper result. The immediate next
gate is `IMPLEMENT_LOCAL_STATIC_MYOPIC_AND_PREDICTIVE_CONTROLLERS`.
