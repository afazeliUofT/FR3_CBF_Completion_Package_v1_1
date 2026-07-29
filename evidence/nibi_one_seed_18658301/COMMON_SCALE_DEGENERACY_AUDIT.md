# Common-scale degeneracy of the pilot allocator

The pilot allocates each sector a received-interference budget in proportion to
its nominal received contribution, then splits that budget between the two
polarization modes in proportion to nominal mode leakage.

Algebraically, the resulting amplitude scale is identical for every sector and
mode at a fixed time:

\[
s_{b,m}(k)=
\sqrt{\frac{I_{\mathrm{allow}}}
{\sum_j \kappa_j(k)L_j}}.
\]

The measured mode-scale spread is numerical noise. The pilot therefore
validates a common oracle DLP reference, not a utility-aware distributed budget
allocator.
