# Independent review of phase-1 campaign candidate v2

## Verdict

`REQUIRES_REVISION_BEFORE_INDEPENDENT_PASS`

Candidate commit:

`f26af9f3ff595f6b6ae9b468c79683e53bc8b450`

Candidate ZIP SHA-256:

`cb4d121372aa572e1163b92d013b87a66d2816180b071a941355c69553e80498`

The architecture mapping, five immutable pass records, manifests, provenance
boundaries, and execution locks pass review. Campaign execution remains
unauthorized.

## Blocking defects

1. The primary engineering envelope is not unique: the candidate lists
   60/65/67 dB caps and 0/1/3 dB uplifts inside the primary design instead of
   freezing one primary scenario.
2. Exact controller information sets and parameters are absent from the
   candidate. Unsafe diagnostics, safe practical comparators, and noncausal
   references are not classified.
3. There is no delayed-myopic comparator with the same reactive
   sector-selective emergency fallback. The unshielded myopic controller is
   useful only as a negative control.
4. The traffic/load contract is a prose label. The exact phase schedule,
   inactive-user PF semantics, stream-rotation rule, and treatment of the
   unequal 571--605-s pass lengths are not frozen.
5. The statistical plan says only “clustered by seed/pass.” The 150 crossed
   cells are not independent, and five pass blocks are too few to bootstrap as
   an iid pass population. The primary estimand, resampling unit, multiplicity,
   missing-run policy, and scope of inference are not sufficiently specified.
6. The candidate does not contain a complete immutable source/config snapshot
   for the controller methods or a compute DAG proving that each channel seed
   will be generated once and reused across passes and methods.
7. Candidate provenance points to the architecture source commit but does not
   freeze the completed five-pass candidate commit.

Candidate v3 repairs these defects while preserving the execution lock.
