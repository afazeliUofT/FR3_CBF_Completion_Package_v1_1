# Rorqual predictive-floor diagnostic recovery

This recovery does not regenerate the H100 channel. It reuses the preserved
seed-43999 channel from Rorqual job 18041525 and submits one CPU-only
diagnostic job. The diagnostic evaluates all five passes and eight methods,
records the exact predictive service-floor violations without enforcing the
hard gate, retrieves a compact review ZIP, and pushes evidence to GitHub.

The immutable reviewed job package is imported read-only. The result is
diagnostic, excluded from confirmatory analysis, and not a paper result.
