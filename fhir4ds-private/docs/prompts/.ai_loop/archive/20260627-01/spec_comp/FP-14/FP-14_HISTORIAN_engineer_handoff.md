# Engineer Handoff - FP-14 HISTORIAN

Issue handled:
- `QA-001` MEDIUM `SPEC_VIOLATION` -> `VERIFIED`

Spec basis:
- FHIRPath 6.2 Comparison defines ordering for DateTime values, requires
  singleton operands, propagates empty operands, and compares supported ordered
  types using their semantic values rather than transport strings.

Root cause:
- The Python fallback comparison pre-processing helper
  `_get_comparison_data()` preserved typed FHIR primitive numerics, but left
  FHIR `date`, `dateTime`/`instant`, and `time` resource strings as plain
  strings. If both operands were resource-backed DateTime strings, `typecheck()`
  saw matching `str` classes and let `_compare()` use Python lexicographic
  ordering. That bypassed `FP_TimeBase.compare()` and timezone normalization.

Fix:
- Updated `fhir4ds/fhirpath/engine/invocations/equality.py` so typed FHIR
  temporal `ResourceNode` strings are materialized as `FP_DateTime`, `FP_Date`,
  or `FP_Time` before comparison.
- Added native-vs-forced-Python fallback regression coverage for all four
  comparison operators over `effectiveDateTime` and `issued` values with
  timezone offsets in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py`.
- Updated `.temp/qa/fp14_historian_fresh_probe.py` to force workspace imports
  and cover the fixed case.

Validation:
- `python3 .temp/qa/fp14_historian_fresh_probe.py` passed, 30 expressions.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py -q` passed, 12/12.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_equality_parity.py -q` passed, 25/25.
- `git diff --check -- fhir4ds/fhirpath extensions/fhirpath fhir4ds-private/docs/prompts/.ai_loop .temp/qa/fp14_historian_fresh_probe.py` passed.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"` passed: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

New issues discovered:
- None.
