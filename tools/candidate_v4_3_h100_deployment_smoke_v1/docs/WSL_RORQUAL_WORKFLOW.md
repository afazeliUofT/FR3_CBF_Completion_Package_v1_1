# WSL and Rorqual workflow

The outer WSL block supplied with the package locates the newest exact package in `C:\Users\alifa\Downloads`, verifies its frozen SHA-256 and portable sidecar, tests ZIP CRC, extracts it, and verifies both internal manifests.

The package wrapper then:

- reuses or repairs the repository `.venv`;
- runs syntax, focused tests, and the independent v4.3 review locally;
- stages source in an isolated clone and uses normal, non-force Git pushes;
- uploads one hash-bound payload to `rsadve1@rorqual.alliancecan.ca`;
- submits one H100 job under an available Rorqual account;
- reuses `/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_SMOKE_5037b4e33448_20260801_031008/run/results/seed_43999/channel`;
- retrieves and verifies a compact return even when the scientific or Slurm exit is nonzero;
- pushes review evidence and opens the Windows return folder.
