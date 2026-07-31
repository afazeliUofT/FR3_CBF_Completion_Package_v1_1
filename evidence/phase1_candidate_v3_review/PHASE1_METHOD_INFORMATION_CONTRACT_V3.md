# Phase-1 method and information contract v3

All methods use the same 64-RF-chain declared architecture, cellular channel,
load state, user floors, update interval, command delay, slew limit, long-term
criterion, paired short-term verification, 65 dB null cap, and 3 dB declared
coupling uplift unless explicitly labelled a noncausal reference.

The primary predictive method may use the preloaded ephemeris-derived future
coupling envelope but not future cellular-channel realizations. The safe static
comparator may use the full-pass envelope once before the pass. A new reactive
myopic baseline receives no future coupling but is given the same
sector-selective emergency fallback. The unshielded delayed-myopic and
virtual-queue methods are diagnostic negative controls, not safety-equivalent
primary comparators.

The instantaneous common-scale method is a noncausal reference and must not be
described as a practical fair baseline. Hard-null/mute and uniform-backoff
methods are conservative safety references.

Every method must report:

- exact information available at each command time;
- command and application time;
- fallback invocation and sector-mute incidence;
- hard-safety ratio at every second;
- eligible-floor violations and normalized shortfall;
- moving-PF utility, protected-band p05/geometric mean, and total-band metrics;
- control variation, signalling payload, and runtime.
