# Engineer Handoff: CQL-18 HISTORIAN

## Scope

- Chunk: CQL-18, List Operators Part 1.
- QA issue: `QA-001` named list definitions bypassed CQL list semantics.
- Remediation status: complete.

## Changes

- Added scalar-list row shape and `List<T>` type inference for CQL list expressions and list-producing operators.
- Routed list-typed identifiers through CQL list helper macros for membership, equality/equivalence, `Distinct`, `Except`, `Exists`, `Flatten`, `First`, `In`, `Includes`, `Included In`, `IndexOf`, and `Intersect` instead of row-set, interval, or raw DuckDB built-in paths.
- Added runtime list equivalence support for non-literal/named lists with CQL element equivalence semantics, including null, normalized strings, and Quantity JSON comparison.
- Added parity regression coverage for forced Python fallback, native-loaded DuckDB registration, and no-Python/browser-style C++ macro/UDF registration.

## Files Touched In This Run

- `.temp/qa/cql18_historian_probe.py`
- `fhir4ds/cql/translator/inference.py`
- `fhir4ds/cql/translator/expressions/_temporal_intervals.py`
- `fhir4ds/cql/translator/expressions/_operators.py`
- `fhir4ds/cql/translator/expressions/_lists.py`
- `fhir4ds/cql/duckdb/macros/list.py`
- `fhir4ds/cql/duckdb/tests/integration/test_list_part1_parity.py`

## Verification

- `python3 .temp/qa/cql18_historian_probe.py` passed.
- `pytest -q fhir4ds/cql/duckdb/tests/integration/test_list_part1_parity.py` passed.
- `pytest -q fhir4ds/cql/tests/unit/test_v2_expressions.py::TestExistsExpression::test_exists_expression fhir4ds/cql/duckdb/tests/integration/test_list_part1_parity.py` passed.
- Full `pytest -q` passed: 7212 passed, 5 skipped, 9 warnings.
- `python3 conformance/scripts/run_all.py` passed: ViewDefinition 134/134, FHIRPath R4 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Notes

- Official XML uses `Flatten(...)`; the fresh probe follows that form for named list definitions.
- Population SQL row-presence assertions intentionally cover non-null boolean rows for singleton-null nullable boolean operators, while direct helper probes cover the SQL NULL boundary.
