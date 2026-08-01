
# System Paths, GitHub, WSL, Nibi, and Rorqual

## Local Windows and WSL

Windows user:

`alifa`

Windows Downloads folder:

`C:\Users\alifa\Downloads`

WSL view of Downloads:

`/mnt/c/Users/alifa/Downloads`

Local WSL repository:

`/home/afazeli2006/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1`

Short form:

`~/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1`

Local virtual environment:

`<repo>/.venv`

Expected local activation:

```bash
cd ~/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1
source .venv/bin/activate
```

## GitHub

HTTPS:

`https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1`

SSH origin used locally:

`git@github.com:afazeliUofT/FR3_CBF_Completion_Package_v1_1.git`

Branch:

`e3-first-sector-p452`

Current head:

`76a62cda5d649cad25a6a45ccb5f0f757a99a269`

Do not push generated large raw arrays blindly. Follow the existing evidence
and ignored-results policy. Every new scientific stage must:

- verify the expected ancestor commit;
- isolate staged paths;
- run `git diff --cached --check`;
- commit and push;
- verify remote/local SHA equality.

## Rorqual

Login:

`ssh rsadve1@rorqual.alliancecan.ca`

User scratch symlink:

`/home/rsadve1/links/scratch`

Resolved scratch seen in the run:

`/lustre10/scratch/rsadve1`

Preserved excluded-smoke root:

`/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_SMOKE_5037b4e33448_20260801_031008`

Preserved environment root used by the port:

`/home/rsadve1/links/scratch/FR3_PHASE1_RORQUAL_ENV_5037b4e33448`

Resolve it with `readlink -f` before use.

Rorqual H100 smoke:

- job `18041525`;
- node `rg21704`;
- one H100-80GB;
- 16 CPU cores;
- 124 GiB host memory requested;
- approximately 2.24 GiB observed MaxRSS;
- failed at predictive service-floor hard gate, not OOM.

Rorqual CPU diagnostic:

- job `18059211`;
- node `rc32306`;
- 16 CPU cores;
- 32 GiB requested;
- approximately 367 MiB observed MaxRSS;
- completed in 1 minute 50 seconds.

Diagnostic local return folder:

`C:\Users\alifa\Downloads\FR3_RORQUAL_FLOOR_DIAGNOSTIC_18041525_20260801_091043`

Diagnostic ZIP:

`FR3_RORQUAL_PREDICTIVE_FLOOR_DIAGNOSTIC_18059211.zip`

Diagnostic ZIP SHA-256:

`428f5e65b701eb645a0cbb1a4fa4138f033f2e308ddcfe918b6bd68b55d3f918`

## Nibi

Login:

`ssh rsadve1@nibi.alliancecan.ca`

Scratch:

`/scratch/rsadve1`

Old pending smoke job observed:

`18906816`

Its later cancellation state is not proven by the packaged evidence. Before any
new Nibi work, check:

```bash
squeue -u "$USER"
sacct -X -j 18906816 \
  --format=JobID,JobName,State,ExitCode,Elapsed,MaxRSS,ReqMem,AllocTRES -P
```

Do not run Nibi and Rorqual workflows that modify the same Git branch
concurrently.

## Command-format rules

The user requires:

- one complete copy-paste WSL block, not fragmented commands;
- every block prints all required diagnostics and exit codes;
- every generated review file is pushed to the GitHub branch when appropriate;
- local versus cluster execution is stated explicitly;
- heavy storage goes to cluster scratch, not HOME;
- Rorqual is preferred over Nibi when GPU queueing is better;
- environment creation and exact version capture are mandatory;
- checksum sidecars must contain portable basenames, not local absolute paths;
- expected nonzero commands must be handled with `if ...; then ... else ...`
  rather than triggering global `ERR` traps;
- failure paths must still retrieve diagnostic ZIPs.
