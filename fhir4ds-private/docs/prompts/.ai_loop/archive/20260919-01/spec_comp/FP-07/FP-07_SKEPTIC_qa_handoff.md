# QA Handoff — FP-07 SKEPTIC (iteration 1, 2026-08-17)

## Chunk
FHIRPath §5.5.4 Date Conversion, §5.5.5 DateTime Conversion, §5.5.6 Decimal
Conversion: toDate(), convertsToDate(), toDateTime(), convertsToDateTime(),
toDecimal(), convertsToDecimal().

## Method
- Normative source: hl7.org/fhirpath/N1 §5.5.4–§5.5.6 (conversion table +
  per-function text) fetched live; official R4 fixtures in
  `fhir4ds/fhirpath/tests/compliance/r4/tests-fhir-r4.xml` (testTypes group
  testString*ConvertsTo{Date,DateTime}, testToDecimal*, testLiteralDecimal*).
- Dual-path probe: 101 + 28 = 129 cases, native extension vs forced Python
  fallback, both via `SELECT fhirpath(?, ?)` (+ is_valid).
  Probe: `/mnt/d/fhir4ds/.temp/qa/fp07_skeptic_2026_08_17/probe.py`.
  Environment: `PYTHONPATH=/mnt/d/fhir4ds` (site-packages trap).

## Results
- ZERO parity diffs (129/129 native == fallback).
- ZERO non-terminal CRITICAL/HIGH/MEDIUM spec violations.
- FP-06 HISTORIAN `\Z` numRegex fix re-verified intact: `'1\n'.toDecimal()`
  → empty in BOTH engines; surrounding grammar corners ('5.', '.5', '1e3',
  ' 1', '1 ', 'NaN', '0xFF', Unicode digits '١٢٣') all rejected by both.
- Date→DateTime precision preserved: `@2015.toDateTime().toString()` →
  `2015T`, `@2015-02` → `2015-02T`, `@2015-02-04` → `2015-02-04T`;
  `= @2015-02-04T` true; time components empty (comparison vs `T00` → empty).
- DateTime→Date truncation correct incl. partials (`@2015-02T` → `2015-02`,
  `@2015T` → `2015`) and timezone (`+10:00`/`Z` dropped).
- toDateTime string grammar strict in both: lowercase `t`, space separator,
  bad month, bad offset `+99:00`, colonless `+1099`, time-only strings all
  rejected; `Z`, `±hh:mm`, >3-digit fractional seconds accepted identically.
- toDecimal: exact Decimal text preserved in BOTH engines at 30+ significant
  digits (`'1.000000000000000000000000000001'.toDecimal().toString()` exact;
  `= 1.0` → false in both); `'+5'`→`5.0`, `'00'`→`0.0`, `'-0.0'`→`-0.0`
  normalization parity; Boolean→`1.0`/`0.0`; Quantity→Decimal empty/false
  (§5.5 table: no Quantity→Decimal conversion), temporal→empty/false; JSON
  integer/decimal primitives convert with exact text (`valueDecimal:1.10` →
  `1.1` per JSON normalization, `multipleBirthInteger` → `2.0`).
- Singleton doctrine: multi-item inputs error → empty at UDF; empty input →
  empty for all six functions.
- 1-arg forms: `toDate(s)`/`toDateTime(s)`/`convertsToDate(s)` treat the
  argument as a FORMAT string (registry arity `1:["String"]`), NOT as input
  (`convertsToDate('2015')` → false in both — evaluates the resource input
  against format '2015'); `convertsToDecimal` has no 1-arg arity (error →
  empty, is_valid=False in both). Consistent, documented.

## Findings (issues)
- QA-001 (LOW, INTENDED — shared convention): `'2015-02-04T14:34'.toDate()`
  returns `2015-02-04` in BOTH engines. Strict spec reading ("convertible
  using the format YYYY-MM-DD") would return empty for dateTime-shaped
  strings, but the same function explicitly converts a DateTime item, and
  both engines share the lenient convention (consistent with the documented
  Date/DateTime-vs-plain-string coercion convention). No official fixture
  pins it. Do not "fix" unilaterally — same class as the FP-01 QA-003
  intentional shared JSON-convenience convention.

## Exit
Zero non-terminal issues; iteration 1 >= min_iterations(1) → CLEAN exit
eligible after FIX/ARCHITECT bookkeeping.
