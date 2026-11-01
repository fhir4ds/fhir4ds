# Engineer Handoff: FP-08 HISTORIAN

Resolved:
- `QA-001` HIGH is fixed and marked `RESOLVED`.

Root cause:
- Native C++ FP-08 conversion functions recognized literal `FPValue::Quantity`
  but did not materialize Quantity-like JSON path values before
  `toQuantity()`, `convertsToQuantity()`, `toString()`, or
  `convertsToString()`.
- Python fallback converted resource Quantity objects only through a loose
  path that accepted invalid non-numeric `value` strings, and `toString()`
  bypassed converted Quantity values.
- Python fallback g/mg unit conversion rounded compatible conversions to an
  integer, making `5 mg -> 0 g`.

Implementation:
- Native `fn_toQuantity`, `fn_convertsToQuantity`, `fn_toString`, and
  `fn_convertsToString` now use strict JSON Quantity materialization.
- Native JSON Quantity parsing now requires finite numeric values and a string
  `code` or `unit`.
- Native `fhirpath_json` Quantity serialization now escapes control
  characters in units and emits ordinary fractional values without the
  observed binary artifact.
- Python fallback ResourceNode/dict Quantity parsing is strict for finite
  numeric values and string units, and `to_quantity`/`to_string` route through
  that parser.
- Python fallback g/mg conversion preserves fractional results.

Validation:
- Fresh probe: `.temp/qa/fp08_historian_probe_after_fix.log` reports
  `cases=39`, `mismatches=0`, `failures=0`.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py -q`
  passed `18`.
- `./build/release/test/unittest "*fhirpath*"` passed `424` native assertions.
- Full conformance passed `2822/2822`.

Changed tests:
- Added resource-backed valid/invalid Quantity conversion parity coverage in
  `test_conversion_parity.py`.
- Added native sqllogictest assertions for resource-backed Quantity conversion
  and string conversion.
