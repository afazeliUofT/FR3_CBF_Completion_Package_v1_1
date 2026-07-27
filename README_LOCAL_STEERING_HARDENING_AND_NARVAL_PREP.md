# Local steering hardening and Narval pilot preparation

Run only:

```bash
bash RUN_LOCAL_STEERING_HARDENING_AND_NARVAL_PREP_DROPIN.sh
```

The master performs every non-heavy task locally in WSL:

1. verifies the current Git branch and frozen inputs;
2. reruns the Sionna port-order audit;
3. freezes exact world-to-local incumbent directions;
4. verifies the negative-phase steering-column convention;
5. builds and statically validates a Narval-only A100 bundle;
6. pushes the source and evidence to GitHub;
7. opens the upload folder.

It does not connect to Narval or Nibi and does not call `sbatch`.

The Narval bundle uses:

- one A100 40 GB GPU;
- 12 CPU cores;
- 124 GB RAM;
- a Narval-only virtual environment;
- eight-user channel-generation chunks to fit one A100.

The older Nibi-oriented FR3 bundle is superseded and must not be run.

The preflight syntax test is deliberately limited to the Python sources installed by this drop-in. It does not scan `.venv`, site-packages, backups, or third-party encoding fixtures elsewhere in the repository.
