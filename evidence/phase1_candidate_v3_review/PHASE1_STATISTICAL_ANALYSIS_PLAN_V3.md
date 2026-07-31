# Phase-1 statistical analysis plan v3

The five pass trajectories are fixed, preselected geometry blocks. They are not
treated as five iid draws from an orbital-pass population.

For seed \(s\) and pass \(p\), let

\[
d_{s,p}=U^{\mathrm{pred}}_{s,p}-U^{\mathrm{static}}_{s,p},
\]

where \(U\) is the final moving-average constrained-PF utility under the exact
same channel, pass, architecture, load, timing, uncertainty envelope, and user
floor policy.

Define

\[
d_s=\frac{1}{5}\sum_{p=1}^{5}d_{s,p}.
\]

The primary estimand is the mean of \(d_s\) over the 30 predeclared channel
seeds. A paired percentile bootstrap resamples the 30 seed clusters 10,000
times. All five pass outcomes for a selected seed are resampled together.

The confirmatory go rule requires:

1. zero predictive hard-safety violation seconds in all 150 seed-pass cells;
2. zero predictive eligible-user floor-violation user-seconds in all cells;
3. all provenance, numerical, manifest, and completeness checks pass; and
4. the lower 95% bootstrap bound for the mean \(d_s\) is greater than zero.

Pass-specific effects and leave-one-pass-out effects are mandatory secondary
reports. They do not expand the primary scope of inference beyond the five
fixed pass blocks. There is one confirmatory utility comparison; all other
method and factor comparisons are secondary or exploratory.

No outcome-based exclusion or imputation is allowed. A deterministic failed
cell may be rerun once with identical immutable inputs. A persistent failure
blocks campaign completion.
