# WSL and Rorqual workflow

The single outer WSL block supplied with the release:

1. selects the newest matching ZIP in `/mnt/c/Users/alifa/Downloads`;
2. verifies the release’s exact SHA-256 and basename-only sidecar;
3. runs `unzip -t`, extracts the package, and verifies both manifests;
4. invokes the packaged WSL orchestrator;
5. activates or creates the existing repository `.venv` and runs syntax,
   focused, exact-data, and randomized local gates;
6. stages and pushes source from an isolated clean clone, leaving the user’s
   current working tree untouched;
7. calls `rsadve1@rorqual.alliancecan.ca` and submits a CPU-only Slurm job;
8. reuses the preserved seed-43999 H100-generated channel and never regenerates
   it;
9. retrieves a compact ZIP and checksum even when the scientific job exits
   nonzero;
10. pushes reviewable evidence without force and opens the Windows return
    folder.

Rorqual is required for the immediate scientific gate because the preserved raw
channel is remote-only. An H100 is not required for this CPU diagnostic.
