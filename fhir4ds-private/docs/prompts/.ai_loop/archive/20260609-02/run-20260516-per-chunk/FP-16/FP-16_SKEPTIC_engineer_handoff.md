# Engineer Handoff - FP-16 SKEPTIC

## Triage
| Issue | Severity | Category | Status |
| --- | --- | --- | --- |
| QA-001 | MEDIUM | SPEC_VIOLATION | RESOLVED |

## Fix
- Spec basis: FHIRPath Normative Release §6.4.2 and §6.4.3 define `in` and `contains` in terms of equality semantics; §6.1.1 defines temporal equality for Dates, Times, and timezone-equivalent DateTimes.
- Root cause: `fhir4ds/fhirpath/engine/invocations/collections.py::contains_impl()` used raw Python `==` for item matching. That bypassed `equality_invocations.equality()` and caused forced Python fallback to return false for temporal values that are equal in FHIRPath.
- Change: `contains_impl()` now checks `equality_invocations.equality(ctx, [item], [candidate]) is True`.
- Tests: added native C++ plus forced Python fallback parity coverage for Date, Time seconds/milliseconds, timezone-equivalent DateTime, and collection forms in `test_collection_operator_parity.py`.
- Native C++ source/binary was not changed; no rebuild was needed.

## Validation
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py -q`
  - Result: `5 passed in 2.59s`.
- `python3 -m pytest fhir4ds/fhirpath/tests/unit fhir4ds/fhirpath/duckdb/tests/unit fhir4ds/fhirpath/duckdb/tests/integration -q`
  - Result: `1218 passed, 1 warning in 37.19s`.
  - Warning: existing `PytestReturnNotNoneWarning` in `test_quantity_udf.py::test_fhirpath_quantity_udf`.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM" > .temp/qa/fp16_validation_summary.log && cat .temp/qa/fp16_validation_summary.log`
  - Result: ViewDefinition `134/134`, FHIRPath `935/935`, CQL `1706/1706`, DQM `47/47`, overall `2822/2822`, all `100.0%`.

## Notes
- The same helper now covers other non-raw-equality cases for membership/containership, including quantity and complex structural equality, without hardcoding temporal literals.
- `fhir4ds/fhirpath/AGENTS.md` was updated with the durable invariant and regression test location.
