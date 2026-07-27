# Sionna PanelArray API recovery

Run only:

```bash
bash RUN_TR38901_MAPPING_AND_NIBI_PILOT_PREP_RECOVERY_DROPIN.sh
```

This recovery resumes after the already-passed TR 38.901 used-subset mapping.

It fixes both affected sources:

- `scripts/31_1_audit_sionna_dual_pol_port_order.py`
- `nibi/dlp_rzf_pilot_v1/run_gpu_pilot.py`

For Sionna 2.0.1, `PanelArray` accepts:

```text
element_vertical_spacing
element_horizontal_spacing
```

The shorter `vertical_spacing` and `horizontal_spacing` names belong to
`AntennaArray`, not `PanelArray`.

The recovery runs a live signature and construction probe in the qualified
Sionna environment, reruns the 128-port dual-polarization audit, rebuilds the
Nibi ZIP, updates evidence, commits, and pushes to GitHub. It does not submit
the H100 job.
