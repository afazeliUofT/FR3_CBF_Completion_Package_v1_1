# Finite-pass delayed reachability safety certificate

## Setting

Index the 114 sector-polarization leakage modes by \(i\). At update interval
\(t\), let

\[
g_i[t]=\frac{\overline c_i[t]}{I_{\rm allow}[t]}
\]

be a certified upper bound on the normalized received contribution of mode
\(i\) before attenuation. The attenuation command is \(q_i[k]\) dB, it is
applied after an integer delay \(d\), and it obeys

\[
0\le q_i[k]\le Q,\qquad
|q_i[k+1]-q_i[k]|\le \rho .
\]

The normalized aggregate interference at application interval \(t\) is

\[
G[t]=\sum_i g_i[t]10^{-q_i[t-d]/10}.
\]

The safety requirement is \(G[t]\le 1\).

## Full-horizon reachability envelope

Let \(a=10^{-\rho/10}\). For the finite protected pass, define the
time-varying envelope for command \(k\) as

\[
e_i[k]
=
\max_{h\ge0:\,k+d+h<T}
g_i[k+d+h]a^h .
\]

The robust safety filter requires

\[
\sum_i e_i[k]10^{-q_i[k]/10}\le1.
\tag{1}
\]

For the pre-pass command used during the first \(d\) intervals, use the same
envelope beginning at application interval zero.

## Theorem

Assume:

1. the true contribution satisfies \(c_i[t]/I_{\rm allow}[t]\le g_i[t]\);
2. a preloaded initial command satisfies (1) for the envelope beginning at
   interval zero;
3. at every update, the selected command satisfies (1) and the slew bound;
4. either \(q_i[k]+\rho\le Q\), or the all-\(Q\) terminal action is certified
   safe for the next envelope.

Then:

- the applied command satisfies the incumbent constraint at every interval;
- the feasible action set is recursively nonempty over the finite pass;
- if a coordinator message is missing, the fail-safe
  \(q_i^{+}=\min(q_i+\rho,Q)\) preserves the certificate under the same upper
  contribution bound.

## Proof

Because the \(h=0\) term is included in the envelope,

\[
e_i[k]\ge g_i[k+d].
\]

Thus (1) directly implies

\[
\sum_i g_i[k+d]10^{-q_i[k]/10}\le1,
\]

which is safety when command \(k\) is applied.

The envelopes satisfy the elementwise recurrence

\[
a\,e_i[k+1]\le e_i[k].
\]

If the next candidate is \(q_i^+=q_i[k]+\rho\), then

\[
10^{-q_i^+/10}=a\,10^{-q_i[k]/10},
\]

and therefore

\[
\sum_i e_i[k+1]10^{-q_i^+/10}
\le
\sum_i e_i[k]10^{-q_i[k]/10}
\le1.
\]

Hence a slew-feasible next action exists. If the upper action bound clips the
candidate, assumption 4 supplies the terminal feasible action. Induction gives
recursive feasibility and safety over the finite pass. The same candidate is
the explicit message-loss fail-safe.

## Robust uncertainty and message age

A multiplicative coupling-error bound of \(\Delta\) dB is incorporated through

\[
\overline c_i[t]=\widehat c_i[t]10^{\Delta/10}.
\]

Additional message age is incorporated by increasing \(d\). No hidden slack is
used: the controller is checked directly against the declared upper
contribution trajectory.

## Interpretation boundary

This is a time-varying discrete robust reachability/barrier certificate for
the incumbent-interference constraint. It does not prove optimality of the
proportional-fair allocation, and it does not yet cover unbounded model error,
unknown traffic outside the declared upper bound, or the final long-term
regulatory functional.
