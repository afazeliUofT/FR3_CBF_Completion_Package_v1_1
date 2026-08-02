# Scientific status and method

The certified v4.4 replay closes 1,213 of 1,736 v4.3 unresolved intervals and
preserves zero long/short EESS violations. It leaves 523 intervals on seven seeds.
Source audit shows all 523 were tested with an incomplete target-only schedule
library: at least one active companion stream in a critical sector had no singleton
service mode. Therefore those LP infeasibility results do not yet justify user
reassignment or admission.

v4.5 completes the singleton basis for every active stream in each critical sector.
The observed worst-case mode count is 625. The action remains fixed-association,
fixed-RZF, floor-first, and bounded to a union of at most four external guards.
Only if this exact completion fails is reassignment/admission the next major choice.
