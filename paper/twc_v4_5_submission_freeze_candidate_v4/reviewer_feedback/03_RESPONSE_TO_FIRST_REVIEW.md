# Response to Independent Reviewer

We thank the reviewer for the careful line-level assessment and for distinguishing provenance and scoping issues from fundamental correctness. We agree with the overall verdict that the work is a strong TWC candidate after mandatory revision. We made no controller, objective, floor, tolerance, seed, or statistical change.

## Mandatory item 1 — SA.1027 thresholds

**Response:** Addressed in Section III-C and the bibliography. We now identify Recommendation ITU-R SA.1027-6, Table 1, as the source of the terrestrial-path criteria for 8 025–8 400 MHz: −150 dBW/10 MHz at 20% and −133 dBW/10 MHz at 0.005%. We state that both criteria are binding and that the evaluated pass begins at 5.012 degrees, above the 5-degree minimum.

We do not present the 57-sector network as normatively one physical interferer. The paper explicitly states that testing its aggregate power as one engineered entry is a conservative study convention; SA.1023 supplies an algebraic apportionment analogy rather than a regulatory classification.

## Mandatory item 2 — SA.509 scope and sensitivity

**Response:** Addressed in Section III-C and Table III. We now state that SA.509-3 is titled for space-research earth stations and radio astronomy, that EESS is not named in its title/scope, and that no measured station pattern is available. The frozen assumed antenna has D = 13 m, G0 = 59.04 dBi, and D/lambda = 353.41, satisfying the Recommendation's D/lambda >= 100 condition.

We added an exact frozen-action single-entry sensitivity. The protected off-axis range lies entirely in the logarithmic sidelobe region, where the single-entry curve is 3 dB above the multiple-entry curve. Applying that peak curve to the frozen candidate traces gives 83,859 long-criterion violation-seconds in all 150 pass cells and zero short-criterion violation-seconds. We therefore scope the primary zero-violation result to the declared aggregate multiple-entry proxy. We do not call the peak curve a certified bound for the actual EESS antenna, because measured data are unavailable and SA.509 is not an EESS-specific mandatory pattern.

## Mandatory item 3 — array description

**Response:** Addressed in Section III-A, Section IX, and the reproducibility package. The physical array is now described consistently as an 8x8 dual-polarized panel with 64 element locations and 128 ports. The stale 16x16 fields in `bs_sectors.csv` and the corresponding unused coherent-array static sensitivity rows have been corrected in `patched_inputs/`.

An audit confirms that the executed generator used the 8x8 configuration and did not consume the stale CSV array dimensions. The primary EESS coupling used the element-pattern reference rows, whose scientific fields are byte-equivalent before and after the patch. No rerun was required.

## Mandatory item 4 — TR 38.901 gate

**Response:** Addressed in Sections II and V. We adopted the reviewer's explicit-scoping alternative. The paper states that the simulation uses the pinned Sionna 2.0.1 UMa implementation, documented by Sionna as based on 3GPP TR 38.901, at 8.15 GHz. We do not claim independent clause-by-clause certification to TR 38.901 V19.4.0, a 3GPP calibration campaign, or universal channel-model validation.

## Mandatory item 5 — P.452 validation and semantics

**Response:** Addressed in Section III-C. We now report that the P.452-18 implementation passes all 17 official ITU-R SG3 validation examples with maximum deviation below 1e-6 dB. We identify the NRCan MRDEM path profiles, the `g=h` terrain/clutter treatment, the absence of a separate P.2108 term, and the use of direct annual-average-year time percentages without worst-month conversion.

## Mandatory item 6 — fixed-service scope

**Response:** Addressed in Section III-C. We state that SRSP-307.7 is included only as Canadian co-band fixed-service context. Fixed-service receivers are outside the protected-service set; the enforced criteria apply only to the modeled EESS earth station.

## Mandatory item 7 — utility magnitude

**Response:** Addressed in Section VI-A. We now interpret the 0.2505 sum-log effect over 228 users as approximately +0.1099% in the epsilon-shifted geometric mean of final moving rates. We explicitly state that this is not an exact raw-rate geometric-mean effect and that the headline contribution is safety plus fairness-burden reduction rather than a large raw-capacity gain.

## Additional terminology corrections

We replaced “pre-registered” with “Git-frozen and pre-specified before holdout execution,” softened “real station” to “public reference geometry,” and avoided describing the SA.509 peak curve as a certified actual-station bound.

## Unchanged scientific content

The following are unchanged:

- candidate-v4.5 source and action hierarchy;
- all floor and EESS definitions;
- delay, slew, power, and locality constraints;
- development and fresh-holdout seeds;
- nine methods and common-random-number structure;
- primary and secondary endpoints;
- bootstrap procedure and reported effects;
- feasibility-conditioned floor semantics.

No cluster was contacted and no new seed or controller run was performed for this revision.
