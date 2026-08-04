# Second-Round Independent Reviewer Verdict

Reviewer expertise: FR3 coexistence modeling; ITU-R/3GPP regulatory
provenance (review performed against an independently archived, SHA-256-
hashed registry of the cited Recommendations); safety-critical control;
robust beamforming; statistics.

Date: 2026-08-04

## Overall recommendation

- [x] READY_FOR_COAUTHOR_APPROVAL_AND_SUBMISSION_FREEZE
- [ ] MINOR_REVISION
- [ ] MAJOR_REVISION
- [ ] NOT_READY

(Readiness includes one recommended 15-minute wording edit and three
optional clauses, listed below; none is a scientific correction and none
should delay the freeze.)

## Mandatory-item closure

| Item | Finding | Verdict | Required correction, if any |
|---:|---|---|---|
| 1 | SA.1027 threshold provenance and aggregation convention | **CLOSED** | None. §III-C now cites SA.1027-6 Table 1 (terrestrial-path criteria, 8 025–8 400 MHz, both criteria binding) and states the pass minimum of 5.012° against the 5° condition — the thresholds match the Recommendation's column exactly per my independently archived copy. The "one engineered sharing entry by study convention" framing (SA.1023 as algebraic analogy, not regulatory classification) is a *more* accurate wording than my first-round suggestion, and I accept the qualification. |
| 2 | SA.509 scope, geometry, and single-entry sensitivity | **CLOSED** | None. Scope sentence present (titled for space research/RAS, EESS unnamed, explicit engineering proxy); geometry stated and internally consistent (13.00 m, G₀ = 59.04 dBi, D/λ = 353.41 ≥ 100 at η = 0.65); the "+3 dB everywhere in the protected window" derivation is mathematically exact (all off-axis > 8.03°, and the single/multiple-entry offset is a uniform 3 dB across the log region and all shelves by the 49-constant structure); Table III reports the frozen-action stress (0 vs 83,859 long violation-seconds; short criterion safe, max ratio 0.081); the 3.01 dB restoration figure is in-text and equals 10·log₁₀ of the audited max ratio 1.99999988. The authors' refusal to call the peak curve a certified *actual-station* bound is scientifically correct given no measured pattern and an unnamed-service proxy — a defensible improvement on my first-round wording. |
| 3 | 8×8 dual-polarized / 128-port array consistency | **CLOSED** | None. `audits/ARRAY_CONSISTENCY_REPAIR_AUDIT.json` proves the executed generator read the 8×8 config and never consumed the stale CSV fields (`generator_uses_bs_sector_csv_array_size_fields: false`; primary κ from element-pattern rows, not the coherent-upper column; scientific fields byte-equal pre/post patch). Patched files hashed; no rerun needed — the correct disposition. |
| 4 | TR 38.901 / Sionna version-bound channel claim | **CLOSED** | None. The explicit-scoping alternative I offered is adopted cleanly: the claim is bound to the pinned Sionna 2.0.1 UMa implementation with its own documentation cited [25]; no independent V19.4.0 clause-by-clause certification, 3GPP calibration, or universal validation is claimed. |
| 5 | P.452 validation and terrain/clutter semantics | **CLOSED** | None. 17/17 official SG3 validation examples at <10⁻⁶ dB deviation plus a 19-link/798-row all-site reconstruction audit; MRDEM profiles; g = h stated with the no-P.2108 no-double-count rule; direct annual average-year percentages declared with worst-month conversion explicitly not applied. All five requested elements are in §III-C with evidence references. |
| 6 | Fixed-service scope | **CLOSED** | None. §III-C: SRSP-307.7 retained as co-band context; fixed-service receivers explicitly outside the protected-service set; the only protected receiver is the EESS earth station. |
| 7 | Per-user utility-effect interpretation | **CLOSED** | None. §VI-A: ≈0.110% increase in the ε-shifted geometric mean over 228 users, explicitly not an exact raw-rate geometric-mean claim, with the headline correctly re-centered on the joint utility/safety/floor-burden result. |

## Claim-boundary checks

- **Aggregate multiple-entry pattern as a study proxy, not certification?**
  Yes — stated in the abstract ("Under the declared aggregate
  multiple-entry earth-station pattern…"), §III-C ("explicit engineering
  proxy rather than a prescribed EESS antenna"), the limitations (item 2),
  and the conclusion. Conditionality is propagated to every claim location.
- **83,859-second result described as frozen-action stress, not a
  reoptimized scenario?** Yes — in the text ("not a re-optimized
  single-entry controller result"), the Table III caption ("re-evaluates
  the frozen candidate actions; it does not re-optimize the controller"),
  and the audit (`scope: frozen-action stress only`).
- **Floor claim limited to feasibility within the declared bounded action
  class?** Yes — unchanged semantics; limitations item 3; 13/30 residual
  seeds retained; the class-vs-physical distinction is intact.
- **Regulatory compliance, hardware calibration, universal TR 38.901
  certification, universal floor feasibility avoided?** Yes — all four are
  explicitly disclaimed ("deterministic engineering tests, not calibration
  or regulatory-compliance evidence"; limitations items 1–4).

## New issues introduced by the revision

One wording exposure, no scientific errors:

1. **Two distinct 3-dB quantities within one column of text.** The
   sensitivity paragraph applies "this 3-dB uplift" (the single-entry
   pattern offset) while eq. (2)'s legend defines "χ the declared 3-dB
   coupling uplift" (the model margin already consumed inside the
   envelope). The antecedent of "this" is clear on careful reading, but a
   fast reviewer could conflate them — or wrongly expect χ to have
   absorbed the pattern offset. Recommended edit (≈15 min): rename the
   sensitivity quantity "the 3-dB pattern offset" throughout §III-C and
   Table III, and add one clause noting the stress is applied *in addition
   to* the already-applied χ. Classified as a recommended pre-freeze
   polish, not a mandatory correction, because the text is technically
   unambiguous as written.

## Mandatory changes before submission

**None.** All seven first-round mandatory findings are closed; no new
correctness, reproducibility, or claim-scope defect was introduced.

## Optional improvements

1. The 3-dB disambiguation edit above (recommended).
2. One clause noting the direction of the g = h choice: omitting
   representative clutter heights on these largely open/rural profiles
   under-predicts diffraction loss and therefore over-predicts
   interference — the protective direction (and, per P.452-18's own Table
   3, open/rural categories carry 0 m anyway, so the omission is small).
3. One clause justifying the annual reading: SA.1027-6 states its
   percentages as unqualified percentage-of-time; the annual average-year
   interpretation with P.452's native annual output is the standard
   SA-series pairing.
4. Report the violation-second *fraction* (83,859/88,140 ≈ 95.1%)
   alongside the count — it makes the "controller rides the long cap, as a
   priced optimizer should" interpretation immediate, and strengthens the
   case that the sensitivity outcome is structural, not a defect.
5. First-round optional items stand (edge/wraparound and array/frequency
   sensitivities; clairvoyant diagnostic; association extensions).

## Final concise verdict

The revision closes all seven mandatory findings with evidence rather than
prose: the thresholds now carry their exact authoritative citation and are
byte-verified against an independently archived copy of SA.1027-6; the
SA.509 usage is scoped, geometrically verified, and — most importantly —
stress-tested, with the frozen-action single-entry result (83,859
long-criterion violation-seconds, max ratio 2.0, 3.01 dB to restore)
reported transparently instead of hidden or spun. That disclosure converts
the paper's largest vulnerability into a quantified claim boundary with an
obvious, stated repair path, and the conditional headline ("zero violations
under the declared aggregate multiple-entry proxy") is now exactly true.
The array metadata inconsistency is proven consumption-irrelevant by audit;
the channel claim is version-bound; the P.452 implementation is validated
against all 17 official examples to 10⁻⁶ dB; and the utility magnitude is
honestly interpreted at ≈0.11% per-user equivalent, with the fairness
result correctly carrying the headline.

Scientifically, the sensitivity outcome is the expected behavior of a
priced optimizing controller — it rides the binding long-term surface with
sub-3-dB margin for ~95% of pass seconds — and the manuscript now says the
right things about what that does and does not imply. No controller,
endpoint, seed, or tolerance changed; the frozen holdout evidence is
intact; package integrity verifies (61 files, all gates PASS).

**Recommendation: READY_FOR_COAUTHOR_APPROVAL_AND_SUBMISSION_FREEZE**, with
the single 3-dB-terminology polish recommended during the freeze pass and
the optional clauses left to author discretion. Confidence: high, on the
same grounds as round one — line-level audit verification, numerical
reproduction of the pattern mathematics, and hash-level agreement with an
independent regulatory archive; no rerun was required.
