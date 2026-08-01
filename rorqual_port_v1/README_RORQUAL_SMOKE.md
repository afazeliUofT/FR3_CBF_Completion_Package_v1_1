# FR3 phase-1 Rorqual noncampaign deployment smoke

This is a cluster-port of the already reviewed immutable phase-1 job package.

It uses:

- login: `rsadve1@rorqual.alliancecan.ca`;
- heavy storage: `/home/rsadve1/links/scratch`;
- exactly one full H100-80GB GPU;
- 16 CPU cores;
- 124 GiB host RAM;
- excluded smoke seed `43999`;
- no Slurm array;
- no confirmatory seed and no phase-1 merge.

The immutable base job-package ZIP is not modified. A copy of its contract is
changed only inside the remote smoke workspace to create a distinct Rorqual
smoke package ID and restrict execution to seed 43999.

Before launching this port, cancel the still-pending Nibi smoke job to avoid
duplicated work:

```bash
scancel 18906816
squeue -j 18906816
```

Then return to local WSL and run the package's runner. The script commits the
Rorqual port source before execution and commits the compact success or
diagnostic return after execution.

The 124 GiB request is deliberately retained for the first Rorqual smoke. On a
Rorqual GPU node (498 GiB, four full H100s), this is approximately one quarter
of node RAM. The completed Slurm record will provide `MaxRSS`, which should be
used to right-size later campaign jobs.
