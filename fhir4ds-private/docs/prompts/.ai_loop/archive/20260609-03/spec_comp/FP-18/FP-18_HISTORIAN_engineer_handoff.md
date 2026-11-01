# Engineer Handoff — FP-18 HISTORIAN

All QA findings were reproduced, fixed, and marked `RESOLVED`.

Fixes:
- `QA-001`: Removed native support for reversed `Quantity +
  Date/DateTime/Time` and made remaining arithmetic with temporal operands
  throw `FHIRPathSpecError` unless it is the valid
  `Date/DateTime/Time +/- Quantity` form.
- `QA-002`: Changed native `fn_dateArith()` unknown-unit handling from empty
  return to `FHIRPathSpecError`, so invalid constant date arithmetic such as
  `@1974-12-25 - 1 'cm'` makes `fhirpath_is_valid()` false while result UDFs
  still return empty/NULL.
- `QA-003`: Added native fixed-scale Decimal text preservation for `+`, `-`,
  and `*` results when operand scale is known, closing `1.2 * 1.8` native
  text/json drift.

Files changed:
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_arithmetic_parity.py`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `.temp/qa/fp18_historian_probe.py`
- `.ai_loop/state/deep_research_findings.md`
- `.ai_loop` handoff/state files and AGENTS notes

Validation:
- Fresh FP-18 HISTORIAN probe: 44 native/fallback/expected cases passed.
- Focused pytest: `test_arithmetic_parity.py` 40 passed.
- Native extension SQL test: 616 assertions passed.
- Full conformance: 2822/2822.
