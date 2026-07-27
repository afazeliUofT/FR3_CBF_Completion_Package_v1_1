# Sionna 2.0.1 qualification hardening and topology-readiness drop-in

Run only:

```bash
bash RUN_SIONNA2_TOPOLOGY_READINESS_DROPIN.sh
```

The drop-in:

1. reruns the qualified UMa/UMi channel APIs and replaces the misleading raw
   maximum-delay statistic with energy-supported delay and RMS-delay metrics;
2. hashes the installed Sionna source modules and records live API signatures;
3. downloads and hashes the official ETSI TR 138 901 V19.4.0 PDF without
   committing the PDF;
4. creates an explicit Release-19 mapping checklist;
5. prepares the frozen finite 19-site/57-sector geometry adapter;
6. runs a one-user-per-sector CPU custom-topology/inter-cell-rate pilot when
   the delay gate passes;
7. pushes every review file to the existing GitHub branch.

The finite adapter pilot uses an 8-port BS array and one UE per sector. It does
not apply DLP-RZF and is not the four-user GPU paper pilot.

The focused energy-weighted delay test is NumPy-only, so the preflight does not require Torch in the project's main virtual environment. Actual Sionna reruns continue to use the separately qualified Sionna environment.

ETSI may return HTTP 403 to command-line clients. The included source wrapper checks existing/browser-downloaded copies, retries with a browser-like session, and provides an interactive browser fallback without leaving the master workflow.
