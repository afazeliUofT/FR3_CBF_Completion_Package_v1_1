# P.452 Project-Specific Pilot Path

This hotfix performs the first project-specific run of the already validated
P.452-18 reference implementation.

It deliberately reuses one audited fixed-service wanted-link path. The pilot
checks profile formatting, terminal heights, units, MATLAB interchange, and
export accounting before a cellular BS-to-incumbent campaign is generated.

It is **not paper evidence** and is **not a cellular interference path**.

## Sequence

1. Run `scripts/21_0_prepare_p452_pilot.py` without `--confirm`.
2. Review the generated terrain PNG, GeoJSON, and checklist.
3. Set all five manual confirmations in `config/p452_pilot.yaml` to `true`.
4. Rerun preparation with `--confirm`.
5. Copy `data/real/p452_pilot` and `matlab/run_p452_pilot.m` to the Windows-native
   validated P.452 execution folder.
6. Run MATLAB R2026a `run_p452_pilot`.
7. Copy the MATLAB outputs back to the repository pilot directory.
8. Run `scripts/20_validate_p452_export.py` on the one-row coupling export.
9. Run `scripts/21_1_validate_p452_pilot.py`.
10. Hash and preserve all pilot evidence.

The next stage after a PASS is to define a standards-parametric modelled UMa
sector layout and build the first actual BS-to-incumbent path, beginning with
E3's local cellular deployment around the tracking earth-station reference case.
