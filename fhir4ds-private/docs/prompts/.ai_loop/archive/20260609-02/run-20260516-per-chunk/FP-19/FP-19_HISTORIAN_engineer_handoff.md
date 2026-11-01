# Engineer Handoff - FP-19 HISTORIAN

Resolved all three QA findings.

Fixes applied:

- `QA-FP19-HISTORIAN-001`: `fhir4ds/fhirpath/engine/__init__.py` now restores `$this` around expression-parameter evaluation; `fhir4ds/fhirpath/engine/invocations/aggregate.py` now restores `$total` and `$index` after `aggregate()`.
- `QA-FP19-HISTORIAN-002`: `fhir4ds/fhirpath/duckdb/evaluator.py` and `fhir4ds/fhirpath/duckdb/udf.py` now strip ignored comments before wrapper syntax heuristics and balance delimiters while ignoring strings, delimited identifiers, and comments.
- `QA-FP19-HISTORIAN-003`: `extensions/fhirpath/src/fhirpath_extension.cpp` now marks owned JSON object/array strings from `yyjson` materialization and only serializes those marked values raw in `fhirpath_json`; ordinary String values are JSON-escaped. Rebuilt and copied `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.

Regression coverage added to `fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py`, `fhir4ds/fhirpath/duckdb/tests/integration/test_aggregate_lexical_parity.py`, and `extensions/fhirpath/test/sql/fhirpath.test`.

Validation passed:

- Focused pytest: 27/27 for aggregate lexical, literal parity, and core conformance regressions.
- Additional parity flank: 14/14 for literal and filter/projection parity.
- Native C++ suite: 276 assertions in 2 test cases.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
