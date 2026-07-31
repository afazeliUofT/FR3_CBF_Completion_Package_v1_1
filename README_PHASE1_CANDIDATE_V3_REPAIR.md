# Phase-1 candidate v3 contract repair

Run only:

```bash
bash RUN_PHASE1_CANDIDATE_V3_REPAIR_DROPIN.sh
```

The stage records the independent round-1 `REQUIRES_REVISION` verdict for
candidate v2, freezes a unique primary engineering scenario, adds exact method,
traffic, statistical, provenance, and compute-DAG contracts, snapshots the
reviewed source/config files, builds candidate v3, and keeps execution locked.

No channel generation, controller campaign, SSH, Slurm, Nibi, Narval, or MATLAB
command is run.
