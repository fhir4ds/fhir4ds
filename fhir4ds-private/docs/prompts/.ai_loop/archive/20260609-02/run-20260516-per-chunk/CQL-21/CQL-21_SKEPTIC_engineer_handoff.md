# Engineer Handoff - CQL-21 SKEPTIC

## Fixed

- Completed Age clinical operator coverage for the requested precision family:
  `AgeInWeeks`, `AgeInWeeksAt`, `AgeInHoursAt`, `AgeInMinutesAt`,
  `AgeInSecondsAt`, and hour/minute/second `CalculateAgeIn*At` fallback
  precision.
- Added static clinical `in CodeSystem` handling for Code, Concept, and String
  operands before generic SQL `IN` fallback.
- Added static Code/Concept/String `in ValueSet` lowering through synthetic
  terminology-bearing resources so the existing native/Python `in_valueset`
  surfaces can evaluate loaded terminology.
- Registered `ExpandValueSet` as a DuckDB macro backed by `valueset_codes` and
  classified it as list-returning so `Count(ExpandValueSet(...))` counts
  expanded codes.
- Added static Code/Concept equality handling so differing component sets return
  SQL NULL instead of false.

## Files Changed

- `AGENTS.md`
- `fhir4ds/cql/duckdb/tests/integration/test_clinical_operator_parity.py`
- `fhir4ds/cql/duckdb/udf/age.py`
- `fhir4ds/cql/duckdb/udf/valueset.py`
- `fhir4ds/cql/translator/expressions/__init__.py`
- `fhir4ds/cql/translator/expressions/_functions.py`
- `fhir4ds/cql/translator/expressions/_operators.py`
- `fhir4ds/cql/translator/expressions/_utils.py`
- `fhir4ds-private/docs/prompts/.ai_loop/evolution.json`
- `fhir4ds-private/docs/prompts/.ai_loop/qa_handoff.md`
- `fhir4ds-private/docs/prompts/.ai_loop/state/deep_research_findings.md`

## Validation

- `pytest fhir4ds/cql/duckdb/tests/integration/test_clinical_operator_parity.py ... test_wasm_cpp_surface.py`: 21 passed.
- `pytest fhir4ds/cql/duckdb/tests/test_arrow_udfs.py fhir4ds/cql/tests/unit/test_parser.py fhir4ds/cql/tests/unit/test_v2_expressions.py`: 239 passed.
- `python3 conformance/scripts/run_all.py`: 2822/2822 overall.
- `pytest fhir4ds/ --tb=short`: 7230 passed, 5 skipped, 9 warnings.
