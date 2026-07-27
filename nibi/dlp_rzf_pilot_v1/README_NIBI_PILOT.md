# Nibi one-seed DLP-RZF GPU pilot

After transferring and extracting the bundle on Nibi, run only:

```bash
bash RUN_NIBI_ONE_SEED_DLP_RZF_PILOT.sh
```

Optional account override:

```bash
SLURM_ACCOUNT=def-rsadve_gpu \
  bash RUN_NIBI_ONE_SEED_DLP_RZF_PILOT.sh
```

The master creates a pinned PyTorch 2.9.1 CUDA 12.8 / Sionna 2.0.1 environment,
submits one H100 job, waits for completion, validates the 57-sector/228-user
DLP-RZF pilot, and creates one return ZIP plus checksum.

This is a one-seed non-paper pilot. It does not compare dynamic controllers.
