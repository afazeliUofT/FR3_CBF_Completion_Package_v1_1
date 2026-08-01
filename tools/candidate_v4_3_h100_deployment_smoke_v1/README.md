# FR3 candidate-v4.3 independent review and excluded H100 smoke

This package performs exactly one next gate:

1. independently re-audit the frozen candidate-v4.3 CPU return for excluded seed 43999;
2. reuse the immutable H100-generated channel on Rorqual;
3. run one H100-node integration replay of all five passes and the eight reviewed methods;
4. reproduce the candidate-v4.3 repair and compare every hard-gate trace with the frozen CPU evidence;
5. collect success or failure evidence and push only reviewable artifacts to `e3-first-sector-p452`.

The candidate controller itself remains the deterministic NumPy/SciPy/HiGHS RRM path. The H100 is used to verify the original deployment environment, CUDA visibility, float64 behavior, and direct access to the preserved physical channel. No channel is generated.

## Frozen result entering this gate

Candidate v4.3 passed the excluded seed-43999 CPU diagnostic:

- zero long- and short-term EESS violations;
- zero floor-violation user-seconds and user-intervals;
- 6 local frozen-grid repairs and 98 fixed-RZF stream-power repairs;
- zero network-wide shutdowns;
- strict post-mode power and strict local action-scope gates passed;
- no deployable use of the broader q=0 power envelope.

The return is bound to SHA-256
`52fbd777e7816320f5bf05ed39ff6c3dd62573776336e404f1f2306875d98e90`
and source commit
`b65dc117f1ace492b55bd764f74bf985fbcb9507`.

## Authorization boundary

This package authorizes only one excluded seed-43999 H100 smoke. It does not authorize seeds 44000–44029, calibration, or a regulatory-compliance claim.
