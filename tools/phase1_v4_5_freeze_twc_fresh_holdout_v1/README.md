# Candidate v4.5 freeze, TWC draft start, and fresh holdout

This package implements the stopping decision after the companion-aware v4.5 development run.
It does **not** add another scheduling library or silently alter the floor.

It performs three linked actions:

1. independently audits and freezes the v4.5 development evidence;
2. stages a concise IEEE TWC manuscript starter and result tables;
3. runs exactly one fresh holdout on seeds 44030--44059 using the frozen v4.5 source.

The primary scientific claim is now feasibility-conditioned user-floor protection under hard EESS safety. Universal zero-floor feasibility is not claimed. User reassignment and serviceability-aware admission are reserved as explicit future remedies if an application requires a universal service guarantee.

The Rorqual request is measured and bounded: one H100, 16 CPUs, 16 GiB, and 10 minutes per seed; the merge and finalizer each request at most 5 minutes.
