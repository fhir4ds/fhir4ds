# Engineer Handoff - CQL-12 EXPLORER

Resolved issues:

- `QA-001` VERIFIED. `Combine` now folds query-shaped sources into a DuckDB
  `list(...)` subquery before invoking `Combine` or `CombineSep`. This fixes
  query-produced `List<String>` compositions such as
  `Combine((from { 'A', null, Lower('B') } S return S), '|')`.
- `QA-002` VERIFIED. Added `escape_fhirpath_string_literal()` and routed
  generated FHIRPath string literals through it for `ext(element, url)`,
  method-form `ext`, fluent `ext`, profile-registry extension paths,
  `FHIRPathBuilder` string predicates, and extension URL existence predicates.
  URL values with escaped quotes now remain literal inside
  `extension.where(url='...')`.

Changed implementation files:

- `fhir4ds/cql/translator/expressions/_functions.py`
- `fhir4ds/cql/translator/expressions/_lists.py`
- `fhir4ds/cql/translator/expressions/_operators.py`
- `fhir4ds/cql/translator/expressions/_utils.py`
- `fhir4ds/cql/translator/fluent_functions.py`
- `fhir4ds/cql/translator/fhirpath_builder.py`

Regression coverage:

- `fhir4ds/cql/duckdb/tests/integration/test_string_operator_parity.py`
- `.temp/qa/cql12_explorer_probe.py`

Validation:

- `python3 .temp/qa/cql12_explorer_probe.py` passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_string_operator_parity.py -q` passed, 7/7.
- `python3 -m pytest fhir4ds/cql/tests/official/test_cql_compliance.py::TestCQLComplianceByCategory::test_string_operators -q` passed, 81/81.
- `python3 conformance/scripts/run_all.py | grep ...` passed full conformance:
  ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47,
  OVERALL 2822/2822.

No new issues were discovered after remediation.

