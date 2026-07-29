# Controller-ready full-topology export preparation

Run only:

```bash
bash RUN_FULL_TOPOLOGY_EXPORT_PREP_DROPIN.sh
```

This local-only drop-in verifies the frozen job-18658301 review package, builds
a self-contained Nibi H100 source bundle for one Sionna topology call with all
228 users, statically validates the source, commits the source and preparation
evidence to GitHub, and opens the bundle folder.

It does not connect to Nibi or submit a job.

The v2 preparation test parses only stage-owned Python files. It does not traverse `.venv`, `site-packages`, backups, or unrelated repository sources.
