# Physical array/CSI calibration requirements

The corrected one-seed controller requires approximately 49--66 dB of
incumbent-parallel attenuation in the long-term cases. The ideal 0--70 dB
numerical grid is not a hardware claim.

Before a practical compatibility or compliance statement, collect or source:

1. complex per-port gain and phase residuals after calibration, versus
   frequency, temperature, time, and calibration age;
2. spatial correlation of those residuals (port, tile, subarray, polarization,
   RF-chain, and common-mode components);
3. phase/amplitude quantization and hybrid-beamforming constraints;
4. achieved OTA null-depth distributions at the protected off-axis angles;
5. mechanical/electrical orientation and steering-direction errors;
6. CSI estimation, reciprocity, delay, and prediction residuals;
7. the practical 64T64R or hybrid architecture and its actual degrees of
   freedom;
8. uncertainty split into held-out calibrated bounds and explicitly declared
   deterministic engineering assumptions.

Use `data/templates/ARRAY_CSI_CALIBRATION_TEMPLATE.csv`. A one-number dB
margin is not sufficient unless its coverage and component composition are
stated and validated.
