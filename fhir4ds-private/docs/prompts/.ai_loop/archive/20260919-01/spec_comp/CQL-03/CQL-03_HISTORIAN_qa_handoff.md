# QA Handoff — CQL-03 Spec Compliance (Temporal and Complex Types), HISTORIAN, iter 1 — 2026-08-20

## Probed (translation + DuckDB execution, C++ native AND Python fallback)
~100 expressions via `.temp/qa/cql03_historian2_2026_08_20/probe{,2}.py` plus a
precision disambiguation follow-up. New angles beyond the SKEPTIC launch:
constructor functions (Date/DateTime/Time incl. partial precision and Decimal
timezone-offset arg), out-of-range constructor components, MinValue/MaxValue,
calendar arithmetic (month-end truncation incl. leap years), UCUM-unit vs
calendar-keyword durations, uncertain-precision ORDERING (`<`/`>`/`<=`),
quantity ordering across converted units, UCUM case-sensitivity lattice,
Ratio tuple-selector constructor + equality/equivalence, Time arithmetic
wrap-around, timezone-normalized equality/equivalence.

## SKEPTIC fix re-verification (both fixes intact, regression-free)
- Strict temporal literal lexing: malformed shapes still rejected at lex time.
- Invalid-unit quantity compare: `5 'xyz' = 5 'xyz'` → null, `~` → false on
  BOTH backends; annotation/compound validity ('{dose}', 'mg/m2', '[pH]')
  intact.

## Verified correct (NOT A BUG, both backends, zero parity diff)
- Constructors preserve partial precision; out-of-range components → null
  (Date(2024,13,1), Date(2023,2,29), Time(25,0,0), ms=1000).
- DateTime ctor vs literal equality/equivalence is precision-driven:
  `DateTime(...,0,2) = @...T10:30:22.000+02:00` → True; ms-vs-second
  precision mismatch → `=` null / `~` false — IDENTICAL to literal-vs-literal
  ms-mismatch semantics (initial suspicion dismissed with evidence).
- Month-end truncation: @2024-01-31 + 1 month → 2024-02-29;
  @2023-01-31 + 1 month → 2023-02-28; @2024-02-29 + 1 year → 2025-02-28.
- Time wrap-around both directions; UCUM 'a'/'d'/'h' duration math on dates;
  precision-coarser unit additions truncate to operand precision.
- Uncertain-precision ordering: comparisons that require missing precision
  → null (@2024-01-15 < @2024-01-15T00, @T14 < @T14:30); decidable ones True.
- Quantity ordering across convertible units (kg>g, cm vs m, m>=100cm);
  dimensional mismatch → null ('mg' vs 'ML' on native both null in the
  INVALID-unit sense — see QA-001 for the case-sensitivity wrinkle).
- Ratio literal equality vs equivalence: `=` component-wise (1:8 ≠ 2:16
  for unit-qualified), `~` proportional (1:2 ~ 2:4 True).
- Decimal timezoneoffset ctor arg + `timezoneoffset from` round-trip.

## Issues filed (evolution.json)
- QA-001 HIGH — quantity same-code comparison validates units against the
  85-entry conversion table (native) / pint (fallback), not the UCUM grammar.
  Valid UCUM codes missing from the table ('G' gauss, 'Mg' megagram, 'MG'
  megagauss, 'ML' megaliter, 'ml'/'l' liter forms, '10*3/uL' power forms)
  → native nulls spec-comparable comparisons; pint accepts INVALID bare
  prefix 'M' → fallback returns True where spec requires null.
- QA-002 HIGH — Ratio tuple-selector constructor emits generic
  `json_object` with raw scalar components and is not classified as Ratio:
  `Ratio { numerator: 1, denominator: 2 } = <identical>` → null (spec true),
  `Ratio{...} ~ 1:2` → false (spec true), mixed tuple-vs-literal `=` → null.
- QA-003 MEDIUM — MinValue/MaxValue(Date/DateTime/Time) pass through as
  untranslated SQL identifiers → DuckDB Catalog Error at runtime instead of
  the spec-defined constant values.

## Handoff to Remediation
QA-001: root-cause fix is structural UCUM validation (metric-prefix + symbol
grammar + `10*n`/`10^n` power prefixes) shared by
`extensions/cql/src/cql/quantity.cpp` `same_code_unit_valid_for_compare()` and
its Python mirror `_same_code_unit_valid_for_compare` in
`fhir4ds/cql/duckdb/udf/quantity.py` (must not fall through to pint when the
shared code is invalid). Native change requires extension rebuild + redeploy
per GLOBAL_RULES.
QA-002: translator `_translate_instance_expression` needs a Ratio branch
emitting canonical FHIR Ratio JSON (quantity-object numerator/denominator,
Integer/Decimal implicit → unit '1'), and `_is_cql_ratio_expr` must classify
Ratio InstanceExpressions so =/~/!= route through ratioCompare.
QA-003: translator-level constant fold for MinValue/MaxValue of
Date/DateTime/Time per CQL 1.5 Appendix B-A.
