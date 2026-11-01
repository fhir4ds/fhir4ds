# CQL-07 EXPLORER Architect Handoff

## Architectural Notes

Conversion operators have two different source categories:

- Data-dependent definitions should remain CTE lookups with patient
  correlation.
- Literal/static definition aliases should preserve scalar expression shape.

The EXPLORER defects came from treating static aliases like data-dependent CTEs
inside conversion operators. That broke standalone translated scalar SQL and
also hid structural UDF type expectations.

## Invariants Added

- CQL conversion functions and `convert ... to ...` may inline a definition
  alias only when the alias body is statically safe: literals, Quantity,
  temporal literals, Code selectors, static structural values, and conversion
  functions over those same static forms.
- Do not inline retrieve/query-dependent expressions through this conversion
  path.
- `convert List<Code> to Concept` must call `ToConceptFromList` with
  `VARCHAR[]`; generated `json_object(...)` Code literals must be cast to
  `VARCHAR` before array construction.
- Native C++ and Python fallback `ToConcept` must agree for object, array, null,
  invalid JSON, and primitive JSON inputs.

## Residual Risk

The static-conversion inliner intentionally uses a conservative whitelist. If a
future static CQL expression class is added and is not whitelisted, it may still
fall back to the older CTE lookup shape until explicitly added with tests.
