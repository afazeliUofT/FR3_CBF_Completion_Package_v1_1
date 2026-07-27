# Narval one-seed DLP-RZF GPU pilot

This package is separate from all Nibi quantum-computing work.

On Narval, run only:

```bash
bash RUN_NARVAL_ONE_SEED_DLP_RZF_PILOT.sh
```

The master:

- creates or validates the Narval-only virtual environment
  `~/.venvs/fr3-sionna2-2.0.1-narval-cu128`;
- requests one full A100 40 GB GPU, 12 CPU cores, and 124 GB RAM;
- generates the large Sionna channel in eight-user chunks to fit one A100;
- validates the 57-sector, 228-user DLP-RZF pilot;
- creates one return ZIP and checksum.

This is a one-seed non-paper pilot.
