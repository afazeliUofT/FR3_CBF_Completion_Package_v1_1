# Distributed incumbent-aware local precoding

## Operational architecture

Each BS computes its own regularized zero-forcing precoder from local UE CSI.
A slow safety layer sends only one scalar received-interference budget to each
BS. The slow layer never receives UE channel vectors or complex precoders.

Let \(W_b^0\) be the nominal local RZF precoder, \(a_b\) the local steering
vector toward the earth station, and \(\kappa_b(t)\) the slow propagation and
earth-station gain factor. The received contribution is

\[
I_b(t)=\kappa_b(t)\|a_b^H W_b(t)\|_2^2.
\]

The local budget \(\beta_b(t)\) gives the transmit-domain target

\[
\gamma_b(t)=\beta_b(t)/\kappa_b(t).
\]

With \(u_b=a_b/\|a_b\|\), decompose

\[
W_b^0=W_{b,\perp}^0+W_{b,\parallel}^0,
\qquad
W_{b,\parallel}^0=u_bu_b^H W_b^0.
\]

The minimum-Frobenius local repair is

\[
W_b^{\rm safe}
=
W_{b,\perp}^0+s_bW_{b,\parallel}^0,
\qquad
s_b=
\min\!\left\{
1,\sqrt{\frac{\gamma_b}{\|a_b^H W_b^0\|_2^2}}
\right\}.
\]

It is closed form, needs no inter-BS CSI, and never increases BS power.

## Aggregate certificate

When every BS enforces \(I_b(t)\le\beta_b(t)\), and the slow layer enforces

\[
\sum_b\beta_b(t)\le I_{\max}(t)-m(t),
\]

then

\[
\sum_b I_b(t)\le I_{\max}(t)-m(t).
\]

The aggregate guarantee therefore follows from independent local actions and a
certified scalar-budget sum.

## Rate-limited implementation

- Local UE precoding can follow the normal scheduler/CSI timescale.
- Scalar budgets change on a slower RRM timescale.
- Between updates, each BS holds the last certified budget.
- On missing or stale messages, each BS uses a preloaded safe schedule or local
  power-backoff fallback.
- Hybrid/codebook implementations must re-evaluate the actual transmitted
  composite precoder after quantization/factorization.

## Claim boundary

RZF, null steering, and Euclidean projection are not individually new. The
paper contribution must be the certified aggregate-to-local decomposition,
dynamic geometry-aware budgets, delayed/rate-limited updates, robustness,
hybrid re-verification, and the resulting safety/utility/runtime evidence.
