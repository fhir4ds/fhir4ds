# Engineer Handoff - FP-14 EXPLORER

Resolved `QA-001` against FHIRPath Section 6.2 comparison semantics and the Section 6.1 DateTime timezone policy discussion.

Fix:
- Patched `fhir4ds/fhirpath/engine/nodes.py::FP_TimeBase.compare`.
- For DateTime comparisons where exactly one side has a timezone offset, the fallback now uses the normalized raw shared-precision fields after stripping the one-sided offset, matching native C++ behavior.
- This avoids falling back to `_getDateTimeInt()` on the original offset-bearing object, which had reintroduced the offset and caused fallback/native drift.

Regression coverage:
- Added `test_one_sided_datetime_timezone_policy_matches_native` to `fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py`.
- The test covers `<`, `>`, `<=`, and `>=` for a one-sided timezone DateTime comparison on native and forced Python fallback connections.

Validation:
- `.temp/qa/fp14_explorer_probe.py`: 28 cases, 0 failures after fix.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py -q`: 10 passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

No new issues were discovered during remediation.
