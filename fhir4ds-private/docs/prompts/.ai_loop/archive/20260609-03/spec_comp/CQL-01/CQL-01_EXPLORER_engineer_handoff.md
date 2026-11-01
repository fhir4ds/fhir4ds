# Engineer Handoff - CQL-01 EXPLORER

Resolved `QA-001`.

## Root Cause

Parameter-derived scalar definitions such as `define I: PI` were not using the
declared parameter type during CQL type inference, so their metadata could fall
back to `Any`. The definition metadata path then treated `Any` as
resource-shaped and seeded `value_column="resource"`. Later CTE synchronization
corrected `has_resource` when the actual CTE did not output a `resource`
column, but left the stale `value_column`, causing final population SQL to bind
`SomeDefinition.resource` for scalar primitive CTEs.

Chained primitive assertions also needed to preserve the source primitive type
through `as Any`/`as System.Any`, because CQL `as Any` is a pass-through for
non-null values and downstream `as Integer` / `as String` must still reflect
the runtime primitive value.

## Fix

- `fhir4ds/cql/translator/inference.py`
  - Parameter identifiers now infer from `context.parameters`.
  - `as Any` / `as System.Any` keeps the source inferred type for downstream
    primitive assertion semantics.
- `fhir4ds/cql/translator/expressions/_query.py`
  - Static structural type inference also preserves the source type through
    `as Any` / `as System.Any`.
- `fhir4ds/cql/translator/translator.py`
  - Metadata synchronization now resets stale `value_column="resource"` to
    `value` when the built CTE does not actually output a resource column.
- `fhir4ds/cql/duckdb/tests/integration/test_primitive_parity.py`
  - Added native-loaded and forced Python fallback regression coverage for
    materialized primitive aliases and `Any` assertion chains.

## Validation

- `python3 .temp/qa/cql01_explorer_probe.py` passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_primitive_parity.py fhir4ds/cql/tests/unit/test_lexer.py -q` passed: 144 passed.
- Full conformance passed: ViewDefinition 134/134, FHIRPath 935/935, CQL
  1706/1706, DQM 47/47, overall 2822/2822.
