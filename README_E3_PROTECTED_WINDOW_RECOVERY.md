# E3 protected-window correction recovery hotfix

## Defect repaired

The v1 wrapper archived `data/real/e3_first_sector_audit/` before
`23_3_rebuild_e3_protected_off_axis.py` read the historical
`selected_sector.json` from that directory. The wrapper then failed with
`FileNotFoundError`.

## Repair

This hotfix:

1. recovers the superseded `E3_SITE_11_SEC_1` selection from the archived
   directory or another agreeing copy;
2. preserves it under `data/real/e3_selection_history/`;
3. preserves the historical unprotected-window off-axis summary under the
   same history directory;
4. updates the correction config to use those stable historical paths;
5. safely resumes the protected-window rebuild, selects
   `E3_SITE_18_SEC_1`, and validates the result;
6. is idempotent for the already-patched source and removes Python caches at
   the end.

The repair changes workflow bookkeeping only. It does not change the
protected-window geometry or the expected corrected selection.
