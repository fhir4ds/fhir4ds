# Engineer Handoff - FP-04 EXPLORER

## Scope

- Workflow: `evolution`
- Phase completed: `FIX`
- Iteration: 1
- Issue handled: `QA-001`

## Triage

| Issue | Severity | Category | Status |
| --- | --- | --- | --- |
| `QA-001` | HIGH | SPEC_VIOLATION | RESOLVED |

## Root Cause

Native DuckDB/C++ `ofType()` delegates superclass checks to
`fhirTypeIsA()` in `extensions/fhirpath/src/fhirpath/evaluator.cpp`. That
embedded hierarchy table covered only a subset of R4 resources, so valid
resources such as `Questionnaire`, `QuestionnaireResponse`, `ValueSet`, and
`CodeSystem` were not recognized as subclasses of `DomainResource`/`Resource`.
The Python fallback uses the generated R4 model hierarchy and kept those
resources.

## Fix

- Expanded the native R4 resource parent relationships in `fhirTypeIsA()`.
- Added generated R4 type names needed by `ofType()` to `isKnownFHIRType()`.
- Added focused native/fallback parity coverage for `ofType(Resource)`,
  `ofType(DomainResource)`, `ofType(Questionnaire)`, and `ofType(ValueSet)`.
- Added a native sqllogictest regression for the same superclass behavior.
- Rebuilt and copied the bundled `fhirpath.duckdb_extension`.

## Validation

- `python3 .temp/qa/fp04_explorer_fresh_probe.py` passed, 28 expressions.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_filter_projection_parity.py -q` passed, 9/9.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py -q` passed, 12/12.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_environment_type_parity.py -q` passed, 11/11.
- `extensions/fhirpath/build/release/test/unittest "*fhirpath*"` passed, 750 assertions.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"` passed:
  ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## New Issues

None.
