# Engineer Handoff — CQL-14 iteration 1

All three QA issues remediated at root cause; dual-engine lockstep maintained.

## QA-001 (MEDIUM) — bare `same as` parse gap → RESOLVED
- Root cause: `fhir4ds/cql/parser/parser.py` handled `same <precision> as` and
  no-precision `same or after/before`, but fell through to identifier for bare
  `same as`; the translator's `"same as"` branch existed but was unreachable.
- Fix: parser now accepts `same as` (grammar: concurrentWithIntervalOperatorPhrase
  with optional dateTimePrecision). Translator `_translate_same_operator`
  "same as" routes point operands to `cqlDateTimeEqual` (min-precision compare
  with uncertainty) and interval operands to start+end `cqlDateTimeEqual`
  conjunction (§9.24 interval Same As).

## QA-002 (LOW) — mixed Time/DateTime pair gave definitive false → RESOLVED
- Root cause: Time-only strings parse with zeroed date components, so
  componentwise compare yielded certain `false` for an undefined operand pair.
- Fix (both engines): `_compare_at_min_precision` and
  `_compare_at_specified_precision` (Python) and `CompareTemporal` (C++) return
  the uncertain result when exactly one operand is Time-only → SQL NULL.
- Native extension rebuilt and deployed; md5 506edd22a83b38fc0237a75263b41050
  (repo bundle = build output).

## QA-003 (LOW) — Now() microsecond precision → RESOLVED
- Root cause: `CAST(CURRENT_TIMESTAMP AS VARCHAR)` carries DuckDB microseconds;
  CQL DateTime model stops at millisecond.
- Fix: fractional seconds truncated to 3 digits via inner regexp_replace in
  translator `now` registration (fhir4ds/cql/translator/expressions/__init__.py)
  and the `Now()` macro (fhir4ds/cql/duckdb/macros/datetime.py).

## Verification
- New focused dual-engine regression:
  `test_datetime_part1_parity.py::test_cql_datetime_part2_same_as_without_precision_and_cross_type`
  (points/intervals/Time/cross-type/Now-ms assertions, py + cpp).
- Full conformance gate: 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706,
  DQM 47) — baseline held.
- fhir4ds/cql/tests 147 passed; cql duckdb full suite run in progress at
  handoff time (datetime/comparison selection: 153 passed earlier).

Files changed: parser.py, _temporal_comparisons.py, udf/datetime.py,
macros/datetime.py, translator/expressions/__init__.py,
extensions/cql/src/cql_extension.cpp (+ rebuilt binary),
test_datetime_part1_parity.py.
