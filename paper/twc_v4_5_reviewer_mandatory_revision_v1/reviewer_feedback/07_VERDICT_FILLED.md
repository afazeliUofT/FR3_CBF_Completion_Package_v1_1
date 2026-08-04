# Independent Reviewer Verdict — FR3 TWC v4.5 (candidate v2)
Expertise: FR3 coexistence modeling, ITU-R/3GPP regulatory provenance,
safety-critical control (CBF/reachability), robust beamforming, statistics.

## Overall verdict

**TWC candidate; major revision required** — with the explicit note that all
mandatory items are provenance, consistency, and scoping repairs. No
fundamental correctness or modeling error was found. After the seven
mandatory items below, this is a strong TWC submission.

## Scores (1–5)

- Novelty and importance: **4** (bounded-local predictive hierarchy with
  exact fixed-beam repair, certificate semantics, and a feasibility-
  conditioned floor claim is a genuine contribution; it deliberately does
  not claim barrier-function novelty)
- Mathematical correctness: **5** (Props 1–3 verified; see finding 6)
- Wireless/system-model fidelity: **4** (frozen E3 UMa layout matched to
  TR 38.901; one array-description inconsistency; V19.4.0 delta gate open)
- Regulatory/technical-source fidelity: **4** (thresholds and SA.509
  numerically verified against independently archived sources; explicit
  citations missing from the manuscript itself)
- Algorithmic practicality: **4** (10.4% scheduling incidence, 0.226 s LP
  max, honest payload lower bounds; near-RT certification correctly not
  claimed)
- Statistical evidence: **5** (frozen pre-registered holdout, paired CRN,
  seed-cluster bootstrap, agreeing secondary endpoint, no exclusions)
- Reproducibility: **5** (immutable job package, per-seed hashes, frozen
  contracts, transparent seed-44052 handling)
- Manuscript clarity and completeness: **4** (excellent claim boundaries;
  missing the provenance statements listed under finding 10)
- Overall TWC suitability: **4.5 after mandatory revisions**

## Required findings

1. **Most important contribution.** The feasibility-conditioned protection
   architecture: hard per-second dual-criterion EESS safety under delay and
   slew (ms §IV-G, Prop. 3), exact fixed-beam LP floor repair (Prop. 1),
   protected-subband scheduling with an unresolved-serviceability
   certificate (Prop. 2, ms §IV-D/H), and the resulting 81.47%/84.76%
   floor-burden reduction at zero EESS violations (Tables III–V).

2. **Strongest evidence.** The frozen fresh 30-seed holdout with
   pre-registered analysis (ms §V-D; `evidence/final_holdout/`): candidate −
   safe-static final PF 0.2505, CI [0.2013, 0.3102]; duration-weighted
   0.2088 [0.1767, 0.2415]; candidate − predictive 0.0563 [0.0205, 0.0967];
   0/0 EESS violation-seconds across all 150 cells; development→holdout
   effect shrinkage moderate (Table IV), exactly as expected of an honest
   freeze. The ablation with a pre-specified stopping rule (Table VII,
   0.76% marginal closure) removes the tuned-to-holdout objection.

3. **Most serious potential flaw.** Not correctness but provenance surface:
   the manuscript presents the two protection thresholds and the SA.509
   pattern as declared engineering choices without their authoritative
   citations, while the package's own catalog flags both
   (`review_protocol/EXTERNAL_SOURCE_CATALOG.csv`: "Potential proxy
   mismatch; claim-critical"; "Package does not itself prove threshold
   derivation"). Cured by mandatory items 1–2 in finding 10. The only
   internal inconsistency found is the array description (finding 10, item 3).

4. **Is the intended incumbent/service model correct?** Yes. The protected
   service is an EESS earth station at 8.15 GHz — inside the 8 025–8 400 MHz
   EESS (space-to-Earth) allocation, hence genuinely co-channel — sited per
   the real Gatineau/Cantley geometry with the network 3–3.5 km south
   (`channel_generator/input/bs_sites.csv`, station_to_site_distance), on
   NRCan MRDEM DTM terrain (provenance notes in the same file;
   `repository/data/external/mrdem/MRDEM_SOURCE_RECORD.json`). SRSP-307.7
   correctly appears only as band-occupancy context; the manuscript should
   add one sentence scoping FS incumbents out (finding 10, item 6).

5. **Are the threshold and antenna-pattern choices defensible?** Yes, with
   mandatory citation repairs. (a) Thresholds: −150 dBW/10 MHz at 20% and
   −133 dBW/10 MHz at 0.005% match Rec. ITU-R SA.1027-6 (08/2019),
   terrestrial-path column for 8 025–8 400 MHz, **exactly**, per the
   program's independently archived, pixel-verified copy; the evaluation
   even begins at 5.01° satellite elevation
   (`earth_station_site_gain_timeseries.csv.gz`, row 1), honoring the
   Recommendation's ≥5° condition without stating it. (b) Pattern: the
   SA.509-3 source PDF in the pipeline is byte-identical to the program's
   registry copy (sha256 839e4caa…5784,
   `repository/data/external/itu/SA509_SOURCE_RECORD.json`), and the
   implementation is numerically exact — off-axis 12.789° → 1.329 dBi
   reproduces the multiple-entry 29 − 25·log10 φ segment to the digit.
   Multiple-entry-as-primary is defensible for a 57-sector aggregate on
   SA.509's own considering-d (peak envelopes overestimate aggregates),
   with RA.769's adoption of SA.509 as service-family precedent. Mandatory:
   state the scope caveat (titled for space-research/RAS, EESS unnamed;
   valid for large parabolic D/λ ≥ 100 — state the station G0/D and verify
   the condition) and report the single-entry (peak) sensitivity in the
   manuscript, since for a hard deterministic test the peak envelope is the
   certified bound.

6. **Is the predictive safety proposition correct and implementation
   matched?** Yes. Prop. 3's backward application envelope
   h_i = max{c_i, α·h_{i+1}} with the delay shift g_t = h_{min{t+d,T}} is a
   valid worst-case invariance argument for this monotone system under the
   3-dB/update slew; it is a finite-pass reachability certificate,
   conditional on the frozen coupling envelope, and the manuscript says so
   in exactly those terms (§IV-G; §IX item 1). The implementation matches:
   `src/fr3_cbf/robust_delayed_safety.py::interval_mode_contributions`
   takes per-second κ, forms **interval-max contributions against
   interval-min allowances** — the correct conservative screening of a 5-s
   command against per-second constraints. Props 1–2 (LP structure after
   cross-multiplication; convex-combination schedule audit with per-mode
   power gates) are sound. Evaluating every method at every physical second
   (§IV-G last ¶) is what makes the negative controls meaningful.

7. **Is the feasibility-conditioned floor claim valid and important?**
   Valid, and one of the paper's best features. The floor (ms eq. (4)) is
   pre-registered and never relaxed; failure semantics separate "safe but
   floor-unresolved" from failure (§IV-H); unresolved cells stay in the
   statistics; the residual 13/30 seeds are diagnosed as joint
   fixed-association incompatibility with **no fixed-beam single-user
   infeasible interval** (§VI-C) — so the class-vs-physical distinction the
   review was asked to scrutinize is properly maintained: infeasibility is
   demonstrated only within the declared bounded action class, and the
   manuscript explicitly refrains from claiming physical infeasibility
   under reassociation or beam redesign (§VIII-B).

8. **Are the baselines and statistics adequate?** Yes. Nine methods with
   matched action spaces, prices, fallbacks, and CRN isolate prediction
   (predictive vs reactive) from repair (candidate vs predictive); the
   noncausal common-scale reference shows future knowledge alone is
   insufficient; unshielded myopic/virtual-queue are correctly framed as
   negative controls (145–152 violation-seconds, Table V). Statistics:
   correct clustering unit (seed), 10,000-replication bootstrap, agreeing
   duration-weighted endpoint, leave-one-pass-out, no outcome-based
   exclusion, transparent seed-44052 wall-time recovery (mean shift
   1.6×10⁻⁴). Optional additions in finding 11.

9. **Are any manuscript claims unsupported or overstated?** No overstated
   claim was found; the boundary discipline (§IX) is above-average for the
   venue. Two under-statements to fix rather than overstatements: the
   utility magnitude needs one interpretation sentence (0.2505 sum-log over
   228 users ≈ +0.1% network geometric-mean rate; Table VI makes the
   fairness result, not raw capacity, the headline), and the ≥5° elevation
   compliance should be stated since it is already implemented.

10. **Mandatory revisions before submission.**
    1. Cite Rec. ITU-R SA.1027-6 (08/2019) as the threshold origin:
       terrestrial-path column, 8 025–8 400 MHz, 10-MHz reference,
       elevation ≥ 5°, both criteria binding, and the network-as-single-
       entry reading (SA.1023 n = 1 collapse) that justifies testing
       aggregate network power against the tabulated level.
    2. SA.509: add the scope statement (space-research/RAS titled, EESS
       unnamed, D/λ ≥ 100 with the station's G0/D stated and checked;
       measured pattern unavailable per the source record's use-boundary),
       and report the single-entry-pattern sensitivity in the paper.
    3. Resolve the array-description inconsistency:
       `channel_generator/input/bs_sectors.csv` declares 16×16 elements at
       8 dBi while `SIONNA_DUAL_POL_PORT_ORDER_AUDIT.json` declares
       8×8 dual-pol/128 ports (0.5λ at exactly 8.150 GHz). One physical
       array everywhere; regenerate or relabel the static reference
       accounting.
    4. Close the package's own TR 38.901 gate
       (`TR38901_USED_SUBSET_MAPPING_DECISION.json`,
       `full_v19_4_certification: false`): review/patch the Rel-19
       7–24 GHz pathloss/O2I/LSP deltas for the used UMa subset, or scope
       the channel claim explicitly to the revision Sionna 2.0.1
       implements, citing V19.4.0 (ETSI PDF hashed in the record).
    5. Report the P.452-18 implementation validation (the register's
       claim-critical item `P452_IMPLEMENTATION`): one manuscript sentence
       on validation against the official SG3 examples, plus the
       terrain/clutter configuration (MRDEM profile; clutter treatment and
       the no-double-count statement) and worst-month/annual semantics.
    6. One sentence scoping the co-band fixed service (SRSP-307.7) out of
       this study's protected-service set.
    7. One sentence interpreting the utility-effect magnitude per user.

11. **Optional changes that should not delay submission.** Finite-network
    edge/wraparound and larger-array/frequency-grid sensitivities (the
    decision record's items b–c); a clairvoyant-envelope diagnostic or
    beam-space reference; association/multi-connectivity extensions
    (already correctly framed as future work, §IX); iid-pass-population
    sampling (the fixed-block limitation is already disclosed, §V-A/§IX).

12. **Final recommendation and confidence.** Major revision, then submit
    to TWC; the mandatory list is mechanical and evidence for every item
    already exists inside the package. Confidence: **high** — grounded in
    line-level verification of the safety code, numerical reproduction of
    the SA.509 pattern, byte-level source-hash agreement with an
    independently maintained regulatory archive, and structural audit of
    the frozen holdout; a computational rerun was not required for this
    verdict.
