# Sector-selective protected-tone backoff certificate

For update interval \(k\), let \(L_b[k]\) be the protected-mode leakage power
of sector \(b\) after clipping the ideal mode-attenuation command to the
declared implementable null-depth cap. Let \(U\ge1\) be the declared residual
coupling uplift. Define

\[
\bar c_b[k]
=\max_{s\in\mathcal I_k}
\frac{U\,\kappa_b[s]L_b[k]}{I_{\rm allow}[s]}.
\]

If the protected-tone sector power scales \(p_b[k]\in[0,1]\) satisfy

\[
\sum_b \bar c_b[k]p_b[k]\le1,
\]

then, for every second \(s\) in interval \(k\),

\[
\frac{U\sum_b\kappa_b[s]L_b[k]p_b[k]}
{I_{\rm allow}[s]}\le1.
\]

The proof is term-by-term from the definition of the per-sector interval
maximum. The certificate is conservative because different sectors may attain
their maxima at different seconds.

Each BS constructs a constrained-proportional-fair local cost curve over its
protected-tone backoff choices. A coordinator broadcasts one scalar price and
each BS selects one local action. The price decomposition is a distributed
feasibility/utility heuristic, not a proof of global optimality. Every selected
action receives an exact full-network per-second safety audit and an exact
eligible-user floor audit.

The exact sector protected-tone mute is an explicit fail-safe endpoint. Its
incidence is reported; it is not hidden slack. The fallback is assumed to be a
pre-authorized local fast action. This stage does not prove that ordinary RRM
signalling can deliver an additional per-sector backoff with a particular
latency or slew rate.

All null-depth caps and coupling uplifts in this stage are declared engineering
scenarios, not measured calibration bounds.
