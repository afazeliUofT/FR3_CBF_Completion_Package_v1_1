# Next Immediate Step

## Gate

`ACQUIRE_OR_DECLARE_ARRAY_CSI_CALIBRATION_ENVELOPE_AND_IMPLEMENT_NULL_FLOOR_AWARE_SECTOR_BACKOFF`

1. Obtain measured or source-referenced per-port complex calibration residuals, their correlation, quantization, steering/orientation error, CSI error, and achieved OTA null depth.
2. If measurements are unavailable, freeze explicit deterministic engineering envelopes and do not claim practical compliance.
3. Implement a null-floor-aware sector-selective protected-tone backoff fallback; uniform backoff remains only a conservative baseline.
4. Re-run the four corrected criterion/pattern cases with the practical null-depth envelope and exact user-floor audit.
5. Independently review the phased campaign bundle before any Nibi submission.
