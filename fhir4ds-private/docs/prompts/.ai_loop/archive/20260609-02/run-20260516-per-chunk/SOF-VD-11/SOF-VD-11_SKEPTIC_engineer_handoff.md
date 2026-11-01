# Engineer Handoff - SOF-VD-11 SKEPTIC

## Triage

| Issue | Severity | Category | Status |
|---|---:|---|---|
| QA-001 | HIGH | SPEC_VIOLATION | RESOLVED |

## Fix

Resolved native/fallback divergence for Observation ViewDefinition execution
with decimal `Quantity.value` columns.

Root cause:
- ViewDefinition runtime type guards evaluate
  `(valueQuantity.value).type().name` for scalar type checks.
- Native C++ returned `decimal`.
- Forced Python fallback returned `string` because `ResourceNode.get_type_info()`
  applied the broad `.value -> string` suffix fallback before using the actual
  numeric value shape when no exact path metadata existed.

Code changes:
- `fhir4ds/fhirpath/engine/nodes.py`: when exact metadata is unavailable,
  numeric and Boolean primitive JSON value shape is trusted before broad suffix
  fallback matches.
- `fhir4ds/fhirpath/engine/evaluators/__init__.py`: `FP_Quantity.value`
  navigation explicitly marks the child node as `decimal`.
- `fhir4ds/fhirpath/duckdb/tests/integration/test_environment_type_parity.py`:
  added native-vs-forced-fallback parity for Quantity.value type reflection.
- `fhir4ds/viewdef/tests/integration/test_duckdb.py`: added a filtered
  Observation ViewDefinition regression projecting `valueQuantity.value` as
  `decimal` on both native and fallback registrations.

## Spec Reference

SQL-on-FHIR v2.0.0 says a View Runner executes a ViewDefinition and returns a
table, and ViewDefinitions include Patient/Observation examples with explicit
column type declarations. Its Column Types section says primitive columns must
be single values when `collection` is not true, and that explicit `type` is the
recommended way for shared ViewDefinitions to make column data type clear.

## Validation

- Fresh QA probe after fix:
  `.temp/qa/sof_vd_11_skeptic_probe_after_fix.json`
- Focused regressions: 2 passed.
- FHIRPath type parity subset: 7 passed.
- Full ViewDefinition pytest: 887 passed.
- FHIRPath unit plus type parity pytest: 183 passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.

No new issues discovered.

