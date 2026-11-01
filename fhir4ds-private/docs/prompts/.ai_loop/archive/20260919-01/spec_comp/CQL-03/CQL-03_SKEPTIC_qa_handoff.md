# QA Handoff — CQL-03 Spec Compliance (Temporal and Complex Types), SKEPTIC, iter 1 — 2026-08-19

## Probed (translation + DuckDB execution, C++ extension AND Python fallback)
~120 expressions via `.temp/qa/cql03_spec_2026_08_19/probe{,2,3}.py`:
literal syntax (partial Date/DateTime/Time forms, offsets Z/+hh:mm/-hh:mm,
fractional seconds); component accessors (dot and `X from` forms); timezone
normalization; uncertain-precision `=`/`~` for Date/DateTime/Time; Quantity
literals, `.value`/`.unit` accessors, UCUM conversion equality, calendar
keywords; Ratio literals (incl. negative num/den), `.numerator`/`.denominator`;
implicit Date→DateTime casting; ToDate/ToDateTime/ToTime/ToQuantity/ToRatio/
convert; ToString of all five types; null propagation.

## Verified correct (NOT A BUG, both backends, zero parity diff)
- All valid partial literal forms round-trip (`@2020`, `@2020-01`, `@T14`,
  `@T14:30`, `@T14:30:22.123`, `@2020-01-01T`, `@2020-01-01T14`, offsets,
  fractional seconds incl. 6 digits).
- Dot component access on temporals is NOT CQL syntax; canonical `year from X`
  etc. all correct (incl. `timezoneoffset from` Z and +hh:mm). Dot access on
  computed temporals returns null (defensible unknown-property semantics).
- Timezone: same-instant equality/equivalence across offsets True; Z → +00:00
  normalization in ToDateTime; no-offset comparisons use evaluation offset.
- Uncertain precision: `=` → null, `~` → false on precision mismatch; same
  precision → True (Date, DateTime, Time all correct).
- Quantity equality across convertible units (cm/m, mg/g), dimensional
  mismatch → null, compound-unit multiply/divide reduction, LHS-unit preserve.
- Ratio: bare-numeric and unit-qualified literals, negative components,
  `=`/`~` spec examples (1:8/2:16), accessor chains.
- Implicit Date→DateTime in comparisons → null (uncertain time components).
- ToString of Date/DateTime(+offset)/Time/Quantity/spec Ratio examples match.
- Null propagation correct across all five types.

## Issues filed (evolution.json)
- QA-001 HIGH — lexer silently accepts malformed temporal literals
  (`@2024-01-15.year` junk-swallow, unpadded `@2024-1-1`, invalid calendar
  `@2024-02-30`/`@2019-02-29`, offset `+99:00`, `+02`). Spec grammar requires
  strict shapes; must raise LexerError.
- QA-002 HIGH — `5 'xyz' = 5 'xyz'` C++ True vs py null (spec: null, invalid
  units); `~` parity diff likewise. quantity.cpp same-code branch skips unit
  validation.
- QA-003 LOW — ToString(Ratio) renders `1.0 '1'` vs ToString(Quantity) `5 'mg'`
  (inconsistent Decimal formatting).

## Handoff to Remediation
Fix QA-001 in `fhir4ds/cql/parser/lexer.py` (strict shape validation), QA-002 in
`extensions/cql/src/cql/quantity.cpp` (is_valid_quantity_unit guard in
quantity_compare same-code branch; requires native rebuild + redeploy per
GLOBAL_RULES). QA-003 at engineer's discretion (cosmetic).
