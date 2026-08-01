# WSL and Rorqual workflow

The one outer WSL block supplied with this release:

1. locates the newest exact-name ZIP in `/mnt/c/Users/alifa/Downloads`;
2. verifies the frozen SHA-256, basename-only sidecar, ZIP CRC, and both
   internal manifests;
3. invokes the packaged WSL orchestrator;
4. activates or creates the repository `.venv` and runs syntax, 18 focused
   tests, prior-v4.2, packaged-diagnostic, original-topology, and randomized
   gates;
5. stages source in an isolated clone and performs normal non-force pushes only
   after checking the current remote branch;
6. calls `rsadve1@rorqual.alliancecan.ca`, uses
   `/home/rsadve1/links/scratch`, and submits one CPU-only Slurm job;
7. reuses the preserved seed-43999 H100-generated channel and never regenerates
   it;
8. handles an expected nonzero scientific exit inside `if`, retrieves a compact
   return and portable checksum, verifies its summary and returned-source
   manifests, pushes reviewable text evidence, and opens the Windows return
   folder.

Rorqual is required for this gate. An H100 is not requested. No confirmatory
seed is submitted or authorized.
