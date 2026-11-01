# Engineer Handoff — Milestone-4 Reconciliation (bug_fix), 2026-08-19

Scope: REV-006 (HIGH) and REV-007 (MEDIUM), per spec_comp/reviews/review-20.md
Part B. Both RESOLVED; exit CLEAN. Conformance 2832/2832 held throughout.

## Situation on resume
A prior reconciliation pass (evaluator.cpp mtime Aug 19 03:45, binary 04:03)
had already re-landed most of the lost fixes BEFORE this session. A symbol +
behavioral audit confirmed present: leastPrecisionDecimalPlaces (FP-13,
both quantityEquivalentState sites), powerDecimalExactText /
powerDecimalGuarded28Text / roundDecimalTextHalfEvenSig /
divideIntegerMagnitudeText / expandScientificToFixed /
shortestRoundTripText (FP-11), DateTimeParts.frac_digits (FP-14),
`target == "Quantity" && !explicit_namespace` isType guard (FP-15, ~line
10809), extension/modifierExtension → Extension at all three fhirFieldType
inference sites (FP-12), evalBinaryOp incompatible-arithmetic throw (FP-19),
and operators.py membership()/contains() FHIRPathError raises (FP-16 / REV-006).
Native probes confirmed each semantic (2.power(3)→'8', 1.0 ~ 1.0001 tolerance
doctrine, 5 'mg' is FHIR.Quantity→false, (1+'x')|99→[],
extension.type().name→'Extension', @T…1234 < @T…1236→true).

## Fixes landed THIS session (extensions/fhirpath/src/fhirpath/evaluator.cpp)

1. **FP-08 EXPLORER QA-002 re-land (REV-007 residual)** — `decimalFactorRatio()`
   (plain-decimal conversion factor → exact integer num/den via shortest
   round-trip text; integral scientific forms like 1000→"1e+03" map to
   den=1) + exact 28-sig ROUND_HALF_EVEN branch in `convertQuantityUnit`'s
   metric path routing through `exactDecimalRatioText` (§4.1.4/§5.5.7).
   From-factor is computed via `convertQuantityToBase(1.0, …)` directly —
   the `from_base_value/value` quotient carries binary64 division noise
   (1000.0000000000001) that silently defeats the exact-ratio guard.
   Fixes `(1 'kPa').toQuantity('mm[Hg]').toString()` 15→28 digits.
2. **Unitless-quantity equality guard (FP-12 HISTORIAN parity)** —
   `jsonValuesEqualState` now returns empty (−1) when a quantity-shaped
   JSON object WITHOUT unit/code (e.g. valueQuantity {"value":120}) is
   compared with `=`/`!=` against a bare JSON number: §6.1.1 defines the
   implicit quantity↔number conversion only for unit '1'. Previously fell
   through to yyjson_equals → false. `~` parity was already correct and is
   untouched. NOTE: fpValueAsQuantity rejects unitless objects, so the fix
   belongs in the JSON comparator, not valuesEqualState.

## Build/deploy
`make release` (extensions/fhirpath); binary md5 57d0634b6ee6eddee9fc06a1355bef5a
deployed to repo bundle `fhir4ds/fhirpath/duckdb/extensions/` and user
site-packages. No `~/.duckdb` linux cache copies existed.

## Validation (Recovery Gate)
- Focused: test_fp08_spec_quantity_time_parity.py + test_tree_utility_parity.py
  + test_conversion_parity.py — 70/70 passed.
- Full integration parity directory: **75 failed / 697 passed → 7 failed /
  765 passed** (review expected ~8). Residual = review bucket c (2
  std::regex named-group/anchor limits) + bucket d (5 temporal-edge
  FALLBACK-side expectation mismatches: @2016 + 1 'a', @2016-01 + 1 'mo',
  @2016-02-29 + 23 hours, @T12 + 1 day, @1974-12-25 - 1 'cm'). The bucket-d
  equality-1 case now passes.
- Conformance master gate: **2832/2832** (ViewDefinition 144, FHIRPath 935,
  CQL 1706, DQM 47).

## Doctrine reconciliation decisions
- None required: no re-landed fix conflicted with a newer campaign pin; the
  two residuals were reconciled toward the newest doctrine (test-pinned
  fallback semantics per FP-08 EXPLORER / FP-12 HISTORIAN).
- Open (untriaged, out of scope): the 5 temporal-edge fallback expectations
  and 2 std::regex limits; pre-existing REV-001..REV-005 findings unchanged.

## New issues discovered
- None. (A transient pytest hang w/ faulthandler dump occurred once during a
  full-directory run and did not reproduce on rerun.)
