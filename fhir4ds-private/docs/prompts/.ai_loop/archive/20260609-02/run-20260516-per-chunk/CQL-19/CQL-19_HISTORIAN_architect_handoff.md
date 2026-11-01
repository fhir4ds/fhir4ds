# Architect Handoff - CQL-19 HISTORIAN

## Scope

Validated the completed QA and remediation loop for CQL-19, HISTORIAN, List
Operators Part 2. The audit covered current source, current official CQL XML,
fresh probes, translated SQL, forced Python fallback, native-loaded
registration, and no-Python/browser-style C++ surfaces. Archived prior workflow
outputs were not used as proof.

## Issue Disposition

- `QA-001` VERIFIED: translated `singleton from` over runtime-produced
  multi-item lists now raises through DuckDB `error()`, while null/empty lists
  return NULL and one-item lists use `LIST_EXTRACT` to preserve element type.
- `QA-002` VERIFIED: query-form `take` now lowers through the public CQL
  `Take` macro, preserving null/non-positive count behavior.
- `QA-003` VERIFIED: list-returning SQL classification includes `Skip`,
  `Take`, `Tail`, `jsonConcat`, and CQL list helper outputs, so nested
  `Length(<null-list chain>)` returns `0`.

No additional architect findings were opened. The QA evidence is sufficient;
`RETRY_QA` is not required.

## Structural Assessment

The remediation stays in the translator/list-boundary layer, which is the right
ownership boundary for the observed failures. No native C++ behavior change was
needed because the public helper surfaces already had the intended semantics
and the native/bundled extension SHA-256 remained unchanged.

The main durable invariant is that translated query syntax must reuse the same
semantic public helper boundaries as direct CQL helper calls. For CQL list
operators this specifically prevents raw DuckDB list built-ins from leaking
different null, slicing, cardinality, Quantity, or element-equality behavior.

## Validation Reviewed

- Fresh probe: `python3 .temp/qa/cql19_historian_probe.py` -> passed.
- Focused parity: `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_list_part2_parity.py -q --tb=short` -> 5 passed.
- List/unit cluster: `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_list_part1_parity.py fhir4ds/cql/duckdb/tests/integration/test_list_part2_parity.py fhir4ds/cql/duckdb/tests/test_list_udfs.py fhir4ds/cql/tests/unit/test_v2_expressions.py -q --tb=short` -> 205 passed.
- Official CQL list category: `python3 -m pytest fhir4ds/cql/tests/official/test_cql_compliance.py::TestCQLComplianceByCategory::test_list_operators -q --tb=short` -> 212 passed.
- Native C++ sqllogictest: `./extensions/cql/build/release/test/unittest '*cql*'` -> 768 assertions passed.
- Full conformance: `python3 conformance/scripts/run_all.py` -> 2822/2822.
- Full pytest: `python3 -m pytest -q --tb=short` -> 7217 passed, 5 skipped, 9 warnings.
- Native/bundled CQL extension SHA-256 matched: `4ba300a57f4b42db9a15e4374c7e40f0932f785dcc92dbd0ad9f463baa9e1f74`.
- Targeted `git diff --check` -> clean.
