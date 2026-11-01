# QA Handoff - CQL-22 HISTORIAN

## Scope

HISTORIAN pass for CQL-22 Errors and Messaging, focused on
`Message(source, condition, code, severity, message)`.

## Spec Basis

CQL 1.5.3 Appendix B, Errors and Messaging, defines `Message` as returning the
input source unchanged. The condition determines whether a diagnostic is
generated, and only `Error` severity stops evaluation; `Trace`, `Message`, and
`Warning` continue.

## Fresh Probes

- Direct `CQLMessage` over forced Python fallback and native-loaded DuckDB.
- Source preservation for integer, Boolean, list, tuple, string, and null
  sources.
- Runtime severity expressions including `lower('Error')` and uppercase
  `ERROR`.
- Translated CQL definitions for `Message`, `Warning`, `Trace`, `Error`, null
  condition, false expression condition, dynamic severity parameter, and null
  source error.

## Results

No issues were found. Both forced Python fallback and native-loaded DuckDB
matched for all fresh probes. Runtime `Error` severity raised; non-error
severities returned the unmodified source.

## Validation

- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_message_parity.py -q`
  passed: 4/4.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py -q`
  passed: 8/8.
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_cql.py | grep ...`
  passed: CQL 1706/1706, including
  `CqlErrorsAndMessagingOperatorsTest.xml: 4/4`.
