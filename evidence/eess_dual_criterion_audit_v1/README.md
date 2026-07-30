# EESS dual-criterion correction audit

Status: `PASS_REGULATORY_DIAGNOSIS_CONTROLLER_REEVALUATION_REQUIRED`

The historical full-topology export combined P.452 p=20% with the -133 dBW/10 MHz
short-term threshold. That hybrid remains useful as algorithmic one-seed
evidence, but it is not the final SA.1027 regulatory test.

Corrected percentile-matched tests:

- long-term terrestrial single-entry criterion: p=20%, -150 dBW/10 MHz;
- short-term terrestrial single-entry criterion: p=0.005%, -133 dBW/10 MHz;
- both must be met.

The all-sector P.452 table already contains p=0.005%, so no new MATLAB/P.452
execution is needed. The next step is a local controller rerun using both
criteria, a provisional 0--70 dB action grid, and a hard-null endpoint. The
SA.509 multiple-entry pattern remains the aggregate-network primary model
decision; the single-entry pattern is a +3 dB protected-window sensitivity.
