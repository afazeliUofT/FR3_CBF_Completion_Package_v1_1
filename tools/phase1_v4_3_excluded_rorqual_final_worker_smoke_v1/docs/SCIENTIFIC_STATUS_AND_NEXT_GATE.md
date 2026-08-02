# Scientific status and next gate

Candidate v4.3 has already passed the excluded CPU feasibility diagnostic and
the preserved-channel Rorqual H100 deployment smoke with zero floor and EESS
violations. The remaining integration gate is the exact immutable final
campaign worker with fresh channel generation.

The previously submitted Nibi job `18953376` was routed to the wrong cluster
and was observed pending for priority in the returned terminal output. It must
be cancelled if still active, and its temporary authorization token must be
removed. Its cancellation is not a scientific failure.

This package runs the exact final worker once on Rorqual for excluded seed
`43999`. On success, the next gate is:

`BUILD_AND_INDEPENDENTLY_REVIEW_RORQUAL_NATIVE_LOCKED_30_SEED_CAMPAIGN_PACKAGE`

The full 30-seed campaign remains unauthorized.
