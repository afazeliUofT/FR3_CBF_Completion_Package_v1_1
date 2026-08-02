# Candidate v4.4 floor-first protected-subband scheduling development

The complete candidate-v4.3 diagnosis found 1,736 unresolved intervals on 11
preserved campaign seeds. Of these, 1,284 are jointly infeasible even for the
global fixed-q/fixed-RZF stream-power LP, while no affected user is individually
infeasible. This package therefore adds the smallest justified new degree of
freedom: bounded protected-subband scheduling after the complete v4.3 repair
hierarchy fails.

The schedule uses physical 0.5-ms NR slots, freezes q commands and RZF
directions, preserves the unchanged floor and EESS tests, and limits deployable
coordination to the current deficit-serving sectors plus one fixed total set of
at most four mute-only external guards. An eight-guard result is diagnostic only.

This is post-campaign development on the 11 observed failures. It does not rerun
the 30-seed campaign, regenerate channels, request a GPU, weaken the floor,
increase scientific tolerances, use q=0 power headroom, or reintroduce
centralized WMMSE. If all 11 development seeds close, freeze v4.4 and start the
13-page TWC draft immediately while a fresh holdout and one compact practicality
study run in parallel.
