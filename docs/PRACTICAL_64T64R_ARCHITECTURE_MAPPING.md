# Generic practical 64T64R and hybrid architecture mapping

The validated 128-port panel contains 64 spatial positions with two
polarizations. The primary declared model maps it to 64 RF chains by forming 32
dual-polarized subarrays. Each subarray contains two adjacent spatial element
pairs and is connected to two RF chains, one per polarization. A fixed
constant-modulus analog subarray beam is aimed at the mean nominal served-user
direction; digital local RZF and the two incumbent-mode controls operate over
the 64 RF-chain outputs.

This construction is consistent with source descriptions of active arrays as
subarrays connected to two radio chains and with 64-chain mid-band massive
MIMO. It is not a replica of any commercial radio. Current 64T64R products may
contain substantially more radiating elements than RF chains.

The primary phase resolution is six bits as a declared engineering case. Eight
bits is evaluated as a sensitivity. A 32-RF-chain, 2x2-subarray model is a
reduced-chain hybrid sensitivity. The 128-port fully digital model remains the
upper reference.

For an active set of at most four users and two protected steering modes, the
64-chain model retains at least 58 digital dimensions after counting those six
constraints. The exact channel rank and steering-mode conditioning are checked
for every load state and frequency.

Sector-selective protected-tone backoff maps to a local baseband scalar applied
before the RF-chain digital precoder; the exact mute endpoint disables only the
protected subband for the selected sector. The 100 ms action-latency budget is
an unmeasured engineering requirement, not a demonstrated implementation.

All null-depth caps, residual uplifts, phase resolution, and latency values are
declared scenarios. No product equivalence, measured calibration, or practical
regulatory-compliance claim is made.
