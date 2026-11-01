# Engineer Handoff — CQL-07 SKEPTIC

## Fixed
QA-001 HIGH: translated CQL `ToString`, `ConvertsToString`, and `convert ... to String` allowed statically known unsupported values to flow into generic SQL String helpers after they had been lowered to JSON/VARCHAR transport. This serialized Interval and Concept implementation JSON instead of returning NULL/false.

## Root Cause
The translator guarded structural List/Tuple/JSON at the SQL macro boundary, but Interval and Concept values can be represented as `VARCHAR` JSON in SQL. Runtime SQL `typeof()` cannot distinguish those from true CQL String values, so the translator must use static CQL type metadata before lowering.

## Change
- Added `_static_type_supports_string_conversion()` in the operator translator utilities.
- Routed translated `ToString` and `ConvertsToString` through the static guard.
- Routed `convert ... to String` through the same static guard.
- Added parity regression coverage for Interval and Concept string conversions.
- Updated root and CQL extension AGENTS guidance.

## Validation
- `python3 .temp/qa/cql07_skeptic_probe.py` passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_conversion_function_parity.py fhir4ds/cql/duckdb/tests/integration/test_conversion_check_parity.py -q` passed: 11 passed.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"` passed: OVERALL 2822/2822.
