# Engineer Handoff - FP-04 SKEPTIC

Phase: FIX
Iteration: 1
Issue count: 1

## Triage

| Issue | Category | Severity | Status |
|---|---|---:|---|
| QA-001 | SPEC_VIOLATION | MEDIUM | RESOLVED |

## Fix

`QA-001` root cause was native `evalOfType` validating the requested type only inside the input loop. `fhirpath_is_valid()` uses a sparse Patient validation resource, so paths such as `entry.resource.ofType(NotAType).id` could have empty input before `ofType` and skip unknown-type validation.

The fix validates the resolved `ofType` type specifier before iterating input, using the existing `fn_isType({}, target_type, exact)` guard. This is spec-grounded in FHIRPath §5.2.4, which requires the type argument to resolve to a model type.

## Validation

- Fresh FP-04 probe: `.temp/qa/fp04_skeptic_probe_after_fix.log`, 14 cases, 0 failures.
- Focused pytest: `test_type_parity.py::test_type_specifier_errors_match_python_fallback` and `test_filter_projection_parity.py`, 6 passed.
- Native FHIRPath unittest: 346 assertions passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Files Touched

- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `.temp/qa/fp04_skeptic_probe.py`
- `.temp/qa/fp04_skeptic_probe_after_fix.log`
- `fhir4ds/fhirpath/AGENTS.md`
- `extensions/fhirpath/AGENTS.md`
