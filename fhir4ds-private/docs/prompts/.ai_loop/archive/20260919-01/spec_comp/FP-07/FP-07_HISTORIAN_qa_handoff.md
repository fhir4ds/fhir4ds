# QA Handoff — FP-07 HISTORIAN (iteration 1, 2026-08-17)

## Chunk
FHIRPath §5.5.4 Date Conversion, §5.5.5 DateTime Conversion, §5.5.6 Decimal
Conversion: toDate(), convertsToDate(), toDateTime(), convertsToDateTime(),
toDecimal(), convertsToDecimal().

## Method
- Normative source: hl7.org/fhirpath/N1 §5.5.4–§5.5.6 (conversion table +
  per-function text), as fetched by the SKEPTIC launch; official R4 fixtures
  in `fhir4ds/fhirpath/tests/compliance/r4/tests-fhir-r4.xml`.
- Dual-path probe: 88 + 19 = 107 fresh cases, native extension vs forced
  Python fallback, both via `SELECT fhirpath(?, ?)` (+ is_valid).
  Probes: `/mnt/d/fhir4ds/.temp/qa/fp07_historian_2026_08_17/probe.py`
  (run with `PYTHONPATH=/mnt/d/fhir4ds` per the site-packages trap).
- HISTORIAN focus: NEW divergence surfaces the SKEPTIC pass did not cover —
  resource-field-driven conversions (model-typed JSON fields incl. the
  `Observation.issued` instant field and partial-precision `effectiveDateTime:
  "2015"`), JSON real/decimal/integer/boolean primitives through toDecimal,
  unexplored lexical corners, and conversion chaining through iteration.

## Results
- ZERO parity diffs (107/107 native == fallback).
- ZERO non-terminal CRITICAL/HIGH/MEDIUM spec violations.
- SKEPTIC fix re-verified regression-free: `'5L\n'.toDecimal()` → empty in
  BOTH engines; `'-5L'`/`'+5L'` → `-5.0`/`5.0`, `'5.5L'`/`'5l'`/`'5LL'`
  rejected identically (longDecimalStringRegex `\Z` anchor intact).
- Resource fields: `birthDate.toDate()/.toDateTime()` (→ `1974-12-25` /
  `1974-12-25T`), instant `issued.toDateTime()` keeps `.123+10:00`,
  `issued.toDate()` truncates, partial year `effectiveDateTime.toDateTime()`
  → `2015T` — all parity-correct.
- JSON primitives: `valueDecimal: 0.1` / `1.10` / `valueInteger: 7` /
  `valueBoolean: true` → toDecimal exact in both; `valueString` → empty/false;
  JSON null field → empty.
- Lexical corners all rejected identically: non-leap `2015-02-29` (leap
  `2016`/`2000` ok, `1900` rejected), `0000`, 5-digit year, day/month 00,
  Apr 31, hour 24, minute/second 60, offset seconds `+10:00:30`, `+14:01`
  (`+14:00` ok), leading/trailing whitespace, CR/tab, single-digit month,
  lowercase `z`, Unicode digits, `'-0'`→`-0.0` parity, `'1 000'`, `''`.
- Chaining: conversions inside `where()`/`select()`/`iif()`, roundtrips
  (`toDate().toDateTime()` → `2015-02-04T`), `'2.5'.toDecimal() * 2` →
  `5.0`, multi-item → empty, `{}` → empty — all correct in both engines.
- is_valid classification consistent on both surfaces for wrong-type fmt
  args, 1-arg `convertsToDecimal` (invalid), and multi-item forms.

## Findings (issues)
- NONE. Zero new issues; no previously pinned convention contradicted.

## Exit
Zero non-terminal issues and iteration 1 >= min_iterations(1) → CLEAN exit
eligible after FIX/ARCHITECT bookkeeping.
