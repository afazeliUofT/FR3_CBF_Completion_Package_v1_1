# Dynamic safety experiment contract

## Purpose

The one-seed pilot proves that the physical/accounting platform is executable.
It does not prove the proposed dynamic contribution. The dynamic experiment
must compare practical controllers under identical update periods, message
delays, information sets, action slew limits, traffic, and uncertainty.

## Control variable

For sector \(b\) and polarization mode \(m\), define a nonnegative attenuation

\[
q_{b,m}[k] = -20\log_{10}s_{b,m}[k]\quad\text{dB},
\]

where \(s_{b,m}\) is the amplitude scale. The received mode power is multiplied
by \(10^{-q_{b,m}[k]/10}\).

With delayed application,

\[
q^{\mathrm{app}}_{b,m}[k]
=
q^{\mathrm{cmd}}_{b,m}[\max(k-d,0)],
\]

and the command obeys

\[
\left|
q^{\mathrm{cmd}}_{b,m}[k+1]
-
q^{\mathrm{cmd}}_{b,m}[k]
\right|
\le \rho.
\]

## Aggregate safety

Let

\[
c_{b,m}[k]=\kappa_b[k]L_{b,m}[k]
\]

be the nominal received contribution before attenuation. Then

\[
I[k]
=
\sum_{b,m}
c_{b,m}[k]
10^{-q^{\mathrm{app}}_{b,m}[k]/10}.
\]

Robust controllers must replace \(c_{b,m}\) by a declared upper coupling. No
hidden emergency slack is permitted.

## Fair comparison

All non-oracle methods receive identical measurements, delay, update period,
slew limit, uncertainty, traffic and local beamformers. A centralized
future-truth method may be shown only as a labelled upper benchmark and must
retain the same actuation delay and slew limit.

## Required dynamic result

The decisive experiment must create a regime where a myopic controller waits
too long and cannot retreat quickly enough because of the slew limit, while a
predictive/CBF controller acts earlier, remains safe and loses less utility
than hard nulling or broad power backoff.

See `config/dynamic_safety_experiment_v1.yaml` for the frozen first grid,
methods, metrics and acceptance boundaries.
