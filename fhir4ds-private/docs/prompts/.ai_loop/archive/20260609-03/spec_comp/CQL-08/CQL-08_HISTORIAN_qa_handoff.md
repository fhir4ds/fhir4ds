# QA Handoff: CQL-08 HISTORIAN

## Scope

Chunk `CQL-08`, personality `HISTORIAN`, covered CQL nullological operators:
`Coalesce`, `IsNull`, `IsFalse`, and `IsTrue`.

## Spec Basis

Consulted the official CQL 1.5.3 reference, Appendix B, Nullological
Operators (`https://cql.hl7.org/09-b-cqlreference.html#nullological-operators-3`)
and the bundled official XML suite
`fhir4ds/cql/tests/official/cql-tests/tests/cql/CqlNullologicalOperatorsTest.xml`.
The relevant rules are:

- `Coalesce` has scalar overloads for 2 through 5 arguments and one
  `List<T>` overload; it returns the first non-null result or null if none.
- `is null` returns true only when the argument evaluates to null.
- `is false` and `is true` return true only for explicit Boolean false/true;
  null and non-Boolean values return false at this public predicate surface.

## Probes

Fresh probe: `.temp/qa/cql08_historian_probe.py`.

The probe exercised:

- Official XML execution cases for string, DateTime, Time, empty-list, scalar
  list-valued, and list-form `Coalesce`.
- Single-list `Coalesce` with more than five elements to verify the scalar
  arity cap is not incorrectly applied to the list overload.
- Direct DuckDB public helper calls on native-loaded and forced Python fallback
  registrations.
- Query-produced list overloads for Boolean and DateTime values.
- Quantity, Code, and Concept values through `Coalesce`, `IsNull`, `IsTrue`,
  and `IsFalse`.
- Dynamic FHIR `Patient.active` true/false/missing cases through infix and
  function forms in population SQL.

## Results

No issues found. Native-loaded and forced Python fallback results matched for
all probe cases.

Validation:

- `PYTHONPATH=. python3 .temp/qa/cql08_historian_probe.py` passed.
- `PYTHONPATH=. python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_nullological_parity.py -q`
  passed: 8/8.
- `PYTHONPATH=. python3 -m pytest fhir4ds/cql/tests/official/test_cql_compliance.py::TestCQLComplianceByCategory::test_nullological_operators -q`
  passed: 22/22.
- `PYTHONPATH=. python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"`
  passed: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.

## Handoff

No remediation required. Continue to no-op engineering handoff and architect
audit/bookkeeping.
