# Next Immediate Step

## Gate

`BUILD_REVIEW_AND_RUN_NONCAMPAIGN_NIBI_DEPLOYMENT_SMOKE`

1. Build a separately reviewed smoke-only WSL-to-Nibi orchestrator.
2. Use a noncampaign seed outside 44000--44029.
3. Freeze and hash the exact Nibi software/GPU environment.
4. Issue a smoke-scoped token bound to package, commit, environment, seed, stage, and expiry.
5. Submit exactly one H100 smoke job and retrieve complete provenance.
6. Independently review the smoke before building the full-campaign orchestrator or issuing a 30-seed token.
