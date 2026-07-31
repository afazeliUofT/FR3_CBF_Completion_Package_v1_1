# Immutable phase-1 Nibi job-package builder

Run only:

```bash
bash RUN_PHASE1_NIBI_JOB_PACKAGE_BUILDER_DROPIN.sh
```

This local-only stage builds, tests, packages, commits, and pushes a locked
Nibi job-array review candidate. It performs one exact local slot-0 smoke test
of all eight methods using the already validated local full-topology dataset.
It does not connect to Nibi and cannot submit any job.

## v2 input-source correction

The builder rehydrates channel-generator inputs directly from the immutable,
reviewed bundle:

`evidence/controller_ready_full_topology_export_prep/FR3_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_NIBI_v1.zip`

It does not require or trust a transient extracted `nibi/.../input` directory.
The reviewed bundle hash, internal manifest, lineage metadata, and all 15 input
hashes are checked before the package is built.
