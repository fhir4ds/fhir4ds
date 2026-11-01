# CQL-03 EXPLORER (launch 2) — QA Handoff

Probe: `.temp/qa/cql03_explorer2_discovery.py` + inline round-2/3 probes. Both
native-loaded (C++ cql.duckdb_extension) and forced Python fallback probed via
`translate_library_to_sql` end-to-end plus direct helper SQL.

Verified-clean surfaces (no issue): tz-offset DateTime equality/ordering/arithmetic
across offsets (incl. +14:00 boundary, normalize-to-UTC, request-offset assumed for
offset-less values), Date↔DateTime precision comparisons (null at precision
mismatch per §Equal "stops and result is null"), Time precision comparisons,
Quantity comparisons (extreme magnitudes, convertible/non-convertible families,
annotations), Quantity scalar arithmetic where compatible, scalar+Quantity unit-1
incompatibility → null, Ratio accessors `.value/.unit` and `.numerator * 2`,
ToQuantity string/numeric forms, temporals in Coalesce/case, Min/Max of
Date/Time lists (incl. null elements), literal boundary dates (leap centuries,
0001, 9999, successor/predecessor null at bounds), E-notation rejection
(NOT A BUG: official fhirpath.g4 `NUMBER: [0-9]+('.' [0-9]+)?` — no exponent),
ToQuantity/ConvertsToQuantity/ToDecimal E-notation rejection (same grammar),
`timezoneoffset from X` (=2.0 for +02:00, 0.0 for Z).

## Issues (all translator/UDF layer, shared by both backends)

- QA-001 HIGH: property-style temporal component accessors return SQL null.
  `(@2024-06-15).month`, `(@2024).year`, `(@T14:30).minute`,
  `(@2024-06-15).date`, `(@2024-06-15T12:30:00).time`, `ToTime('T14').hour` →
  null on both backends. `month from X` works. Root cause: `_translate_property`
  lowers temporal components to `fhirpath_text(<literal>, 'month')` instead of
  `dateComponent`. Spec §09-b Date/Time Component From (`.year`, `.month`, ...).
- QA-002 HIGH: define-alias of a temporal literal then accessor
  (`define D: @2024-06-15` `define Result: D.month`) emits
  `fhirpath_text((SELECT sub.value FROM "D" sub WHERE sub.patient_id =
  _pt.patient_id LIMIT 1), 'month')` against patient-less literal CTE `D` →
  Binder Error end-to-end on both backends (static-literal-define alias
  inlining gap; CQL-02 noted the same family for String/Integer defines).
- QA-003 HIGH: seconds/milliseconds must combine as ONE decimal precision in
  comparisons ("with the seconds and milliseconds combined and represented as
  a Decimal for the purposes of comparison"; unspecified ms treated as 0).
  `@T10:00:00.0 = @T10:00:00` → null (expect true);
  `@2024-11-15T12:30:00.5 = @2024-11-15T12:30:00` → null (expect false);
  `@2024-11-15T12:30:00.0 = @2024-11-15T12:30:00` → null (expect true).
  `@T10:00:00.500 = @T10:00:00.5` is correctly true. Layer: cqlDateTimeEqual
  (Python fallback + C++ extension both affected).
- QA-004 MEDIUM: `.numerator`/`.denominator` accessors lose Quantity type
  metadata; `ToRatio('10 ''mg'':2 ''mL''').numerator + 5 'mg'` lowers to
  `dateAddQuantity(CAST(fhirpath_text(...,'numerator') AS VARCHAR), <qty>)`
  → null (expect 15 'mg'). `.numerator * 2` works numerically. Spec §Ratio:
  numerator/denominator are Quantity.
- QA-005 MEDIUM: `.timezoneoffset` property accessor rejected by parser
  (`Expected identifier, got TIMEZONE_FROM 'timezoneOffset'`), both casing
  forms. Official cql.g4 lists 'timezoneoffset' as a dateTimeComponent AND
  keywordIdentifier (valid property). `timezoneoffset from X` already works.
