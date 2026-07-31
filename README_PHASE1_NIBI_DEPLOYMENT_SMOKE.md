# Noncampaign phase-1 Nibi deployment smoke

Run only:

```bash
bash RUN_PHASE1_NIBI_DEPLOYMENT_SMOKE_DROPIN.sh
```

The wrapper first builds, validates, commits, and pushes the reviewed smoke
orchestrator. It then connects from local WSL to Nibi, freezes the exact
software environment, creates a smoke-only authorization token, submits one
H100 job for excluded seed `43999`, retrieves a compact return/diagnostic ZIP,
and validates it locally.

The 30 confirmatory seeds, campaign array, and campaign merge remain locked.
