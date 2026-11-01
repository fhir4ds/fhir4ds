# Architect Handoff - FP-15 HISTORIAN

Chunk: FP-15, FHIRPath §6.3 Types
Personality: HISTORIAN
Audit status: COMPLETE
Architect findings: 1
`RETRY_QA`: false

## Findings

- `ARCH-001` (MEDIUM, RESOLVED): `value[x]` exact `as` semantics across surfaces.

The FP-15 code now preserves `FHIRPath` choice semantics for `as(string)` while keeping
`valueUri is string` behavior intact for hierarchy checks. The native evaluator was
updated to use stored `fhir_type` metadata in exact string target branches before
falling back to field-name heuristics. This prevents concretely-typed `valueUri`
from being treated as exact `string` in `as(string)` assertions.

## Validation

- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_environment_type_parity.py::test_uri_reference_and_media_type_shapes_match_cpp -q`
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py::test_choice_type_assertion_after_resource_oftype_matches_fallback -q`
- Targeted Python probe for `Parameters.parameter[0].value.as(string)` and `.as(uri)` parity between native/forced-fallback.
