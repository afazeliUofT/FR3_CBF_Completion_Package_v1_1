# Candidate v4.3 Rorqual 30-seed campaign authorization and execution

This package is the separately reviewed authorization/orchestration layer for the exact immutable `V4_3_RORQUAL_R2` campaign package.

It authorizes only:

- Rorqual;
- seeds 44000--44029;
- five fixed pass records;
- nine frozen methods;
- the exact candidate-v4.3 source and corrected R2 validators;
- array `0-29%8`, one H100 per seed task;
- an `afterany` failure-preserving merge.

It does not change candidate v4.3, does not reuse channels, does not claim calibration or regulatory compliance, and does not certify information-exchange locality. The generated authorization token is short-lived, is never returned, and is deleted after the campaign jobs finish.
