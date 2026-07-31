# Finite-pass delayed reachability safety certificate

## Setting

Index the 114 sector-polarization leakage modes by \(i\). At update interval
\(t\), let

\[
g_i[t]=\frac{\overline c_i[t]}{I_{\rm allow}[t]}
\]

be a certified upper bound on the normalized received contribution of mode
\(i\) before attenuation. The attenuation command is \(q_i[k]\) dB, is
applied after an integer delay \(d\), and obeys

\[
0\le q_i[k]\le Q,\qquad
|q_i[k+1]-q_i[k]|\le \rho.
\]

The normalized aggregate interference at application interval \(t\) is

\[
G[t]=\sum_i g_i[t]10^{-q_i[t-d]/10},
\]

where a preloaded command is used before the first commanded action arrives.
The safety requirement is \(G[t]\le 1\).

## Application and command envelopes

Let \(a=10^{-\rho/10}\). For a finite protected pass of \(T\) update
intervals, define the application envelope

\[
E_i[t]=\max_{r\in\{t,\ldots,T-1\}} g_i[r]a^{r-t}.
\]

It satisfies

\[
E_i[t]\ge g_i[t],\qquad aE_i[t+1]\le E_i[t].
\]

The envelope attached to command index \(k\) is

\[
e_i[k]=E_i[\min(k+d,T-1)].
\]

The command selected before the protected pass uses \(E_i[0]\). Every later
command must satisfy

\[
\sum_i e_i[k]10^{-q_i[k]/10}\le 1.
\tag{1}
\]

## Corrected saturation-aware theorem

Define the explicit ramp-to-safe candidate

\[
F_i(q)=\min(q_i+\rho,Q).
\]

Assume:

1. the true contribution satisfies
   \(c_i[t]/I_{\rm allow}[t]\le g_i[t]\);
2. the preloaded command satisfies
   \(\sum_i E_i[0]10^{-q_i^{\rm pre}/10}\le1\);
3. every selected command satisfies (1), the box constraint, and the slew
   constraint relative to the preceding command;
4. for every nonterminal command index, the *actual clipped candidate* obeys

   \[
   \sum_i e_i[k+1]10^{-F_i(q[k])/10}\le1.
   \tag{2}
   \]

Then the applied actions satisfy the incumbent constraint throughout the
finite pass, the feasible command set remains nonempty at every update, and a
missing coordinator command can be replaced by \(F(q[k])\) without violating
the same certificate.

## Proof

A command \(q[k]\) is applied at interval \(k+d\). Because
\(e_i[k]=E_i[k+d]\ge g_i[k+d]\), (1) implies

\[
\sum_i g_i[k+d]10^{-q_i[k]/10}\le1.
\]

The preloaded action gives the same statement for the first \(d\) application
intervals.

If no component saturates at \(Q\), then \(F_i(q)=q_i+\rho\), and

\[
10^{-F_i(q)/10}=a10^{-q_i/10}.
\]

Using \(a e_i[k+1]\le e_i[k]\) gives

\[
\sum_i e_i[k+1]10^{-F_i(q[k])/10}
\le
\sum_i e_i[k]10^{-q_i[k]/10}
\le1.
\]

When one or more components saturate, the preceding algebra does not by itself
certify the clipped vector. Assumption (2) explicitly checks that exact
slew-feasible candidate. Thus a feasible next action exists in either case.
Induction establishes recursive feasibility and safety over the finite pass.
The same candidate is the declared message-loss fail-safe.

## Robust uncertainty and message age

A multiplicative coupling-error bound of \(\Delta\) dB is incorporated as

\[
\overline c_i[t]=\widehat c_i[t]10^{\Delta/10}.
\]

Additional known message age is incorporated by increasing \(d\). No hidden
slack is used: the filter is checked against the declared upper contribution
trajectory.

## Interpretation boundary

This is a finite-pass, time-varying, discrete robust reachability/barrier
certificate for the incumbent-interference constraint. It proves safety and
recursive feasibility under the stated upper trajectory, delay, slew, and
candidate-specific saturation checks. It does not prove proportional-fair
optimality, calibrate the uncertainty bound, cover unknown traffic outside the
declared envelope, or resolve the final long-term regulatory functional.
