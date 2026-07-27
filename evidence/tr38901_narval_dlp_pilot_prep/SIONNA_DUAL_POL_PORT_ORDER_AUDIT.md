# Sionna dual-polarized port-order audit

- Status: `PASS_SIONNA_DUAL_POLARIZATION_PORT_ORDER_AND_BASIS`
- Ports: `128`
- Ports per polarization: `64`
- Position duplication error: `0.000e+00` m
- Polarization-mode inner product: `0.000e+00`

The GPU pilot must use the exported `ant_ind_pol1` and `ant_ind_pol2` sets rather than assuming alternating port order.
