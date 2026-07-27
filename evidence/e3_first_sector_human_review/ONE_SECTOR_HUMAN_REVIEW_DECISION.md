# Independent review of the Site-18 one-sector P.452 accounting audit

- Verdict: `PASS_WITH_REQUIRED_NEXT_STAGE_CONSTRAINTS`
- Sector: `E3_SITE_18_SEC_1`
- Claim boundary: `PASS_AS_ACCOUNTING_AUDIT_NOT_PAPER_RESULT`
- P.452 rows checked: `42`
- Earth-station gain rows checked: `3522`
- Accounting rows checked: `49308`
- Maximum full-row accounting error: `2.842e-14 dB`
- Maximum SA.509 recomputation error: `8.882e-15 dB`
- Coast-distance loss span: `0.000e+00 dB`
- H/V loss span: `0.000e+00 dB`
- P.452 p=50 minus free-space reference: `-0.011493 dB`

## Human-review finding

The basic-loss and gain/power accounting are internally correct under the
declared assumptions. The result remains a one-sector accounting audit, not a
paper result or compliance determination.

Every declared full-power reference case exceeds both thresholds for every
protected-window sample. This is a real result of the close-in stress geometry,
not a software error. The final paper therefore needs actual composite-beam
gains and a non-degeneracy/feasibility analysis; the coherent-array envelope
must not be used as the final system result.

The existing `peak_accounting_components.csv` corresponds to the nominal
p=20%, H, coherent-array, multiple-entry-pattern peak. It is not the global
conditional peak. Precisely named replacement files are included.

## Next gate

`HUMAN_REVIEW_OF_ALL_19_SITE_TERRAIN_BEFORE_P452_SCALING`
