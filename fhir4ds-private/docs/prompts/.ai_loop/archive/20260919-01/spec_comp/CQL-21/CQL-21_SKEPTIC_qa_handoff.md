# QA Handoff — CQL-21 (Clinical Operators), SKEPTIC, iteration 1

## Spec anchors verified (live 2019May/2.0 build Appendix B + official cqframework/cql-tests XML suite)
- Age/AgeAt/CalculateAge/CalculateAgeAt: each defined AS a duration calculation; partial birthDate (or partial asOf) below operator precision → **uncertainty over the range**; AgeInYears/Months use Today(), finer precisions use Now(); Age/AgeAt are shorthand for CalculateAgeIn...At with Patient-context birthDate. Official XML test suite has NO age tests (requires patient context), so spec text is the sole anchor.
- Equal (Code/Concept): tuple equality (all elements by name, order-sensitive codes list, null if different components). Equivalent: Code code+system only (string equivalence); Concept non-empty code intersection; null~null true; empty concept NOT equivalent to null concept.
- In(CodeSystem)/In(ValueSet)/ExpandValueSet: 1.5 `in` semantics; unresolved reference → runtime error; null code → false.

## Findings
- **QA-001 (HIGH, OPEN)**: Entire age-operator family bypasses the engine's own §22.21 duration-uncertainty semantics and uses a crisp day-1 partial-birthDate convention (Jan 1 / day 1), on BOTH Python and native C++ paths and all translator surfaces:
  - translator bare `AgeIn*()` → `YearsBetween`/`MonthsBetween`/... crisp UDFs (not `cqlDurationBetween`)
  - one-arg `AgeIn*At(asOf)` → `CalculateAgeIn*At` UDF (crisp)
  - direct `CalculateAgeIn*`/`*At` UDFs (crisp)
  - two-arg `AgeIn*At(resource, asOf)` UDFs (crisp)
  Evidence: `CalculateAgeInYearsAt('2012','2026-05-14')` = 14 vs `cqlDurationBetween('2012','2026-05-14','year')` = `{"start":13,"end":14}`; end-to-end Patient birthDate '1990' `AgeInYearsAt(@2026-05-14)` = 36 crisp (range [35,36]) on py+cpp. Comparisons on age results get plain SQL compare, not `cqlUncertainCompare`.
- Verified clean (NOT A BUG): Equal/Equivalent Code+Concept full CQL-02 boundary matrix intact; In(CS)/In(VS)/ExpandValueSet static + runtime-cache paths intact; leap-day anniversary semantics; negative-age → null convention (documented, spec-silent); AgeInHoursAt tz-aware asOf; CalculateAgeIn*At null propagation; all 15 test_clinical_operator_parity.py tests pass pre-fix.

## Probes
`.temp/qa/cql21_probe{,2,3,4,5,6}.py`

## Recommended fix shape
Route all age surfaces through the duration-with-uncertainty engine (`cqlDurationBetween` semantics, VARCHAR int-or-interval-JSON, collapse-when-determinate) in Python UDFs, native C++ UDFs, and the translator (bare + one-arg At paths emit `cqlDurationBetween`; extend uncertain-comparison/arithmetic detection to age expressions). Preserve negative-age→null and full-precision behavior (identical results for day-precise birthDates, so existing pins like (26,)/(313,) keep semantics but become VARCHAR strings — tests need updating).
