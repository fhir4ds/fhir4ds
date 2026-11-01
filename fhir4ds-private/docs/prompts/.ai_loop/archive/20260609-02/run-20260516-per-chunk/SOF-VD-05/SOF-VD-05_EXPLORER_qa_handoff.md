# QA Handoff: SOF-VD-05 EXPLORER

## Scope

Executed EXPLORER audit for SQL-on-FHIR ViewDefinition nested
`select`/`unionAll` behavior. This pass used fresh probes against the active
codebase only; archived workflow outputs were not used as evidence.

Spec references were checked against the current SQL-on-FHIR IG:
- `ViewDefinition.select.select` is a recursive `contentReference` to
  `ViewDefinition.select`.
- Functional model row composition says nested selects inherit the parent
  context, sibling selects cross-join, parent columns repeat with child rows,
  and `unionAll` branches must produce the same number of columns with the same
  names, order, and FHIR types.

## Probes

- Parser/generator shape checks for nested `select`, `unionAll`, and direct
  dataclass bypasses.
- DuckDB execution for nested select recursion, default `$this` context,
  parent/child row combination, sibling cross-join, nested `forEach` under
  `forEachOrNull`, and empty nested select combinations.
- Native C++ registration and forced Python fallback registration were both
  exercised for DuckDB probes. In this environment `register_fhirpath()` returns
  `True` only when the connection is created with
  `allow_unsigned_extensions=True`; forced fallback was verified by monkeypatching
  `duckdb.__version__`.
- Relevant official ViewDefinition conformance was rerun:
  `python3 conformance/scripts/run_viewdef.py | grep -E ...`, producing
  `Summary: 134/134 tests passed (100.0%)`.

## Findings

### QA-001 MEDIUM OPEN

`unionAll` branch validation checks output column names/order but does not check
declared FHIR type or `collection` cardinality. Spec-invalid branch schemas such
as `value:id` versus `value:integer`, or scalar versus collection, are accepted
by `SQLGenerator.generate()`.

### QA-002 LOW OPEN

Direct dataclass generation can bypass recursive select container shape
validation. `Select(select=None)` raises a raw `TypeError`,
`Select(select={"bad": "shape"})` and `Select(column={...})` raise raw
`AttributeError`, and `Select(unionAll=None)` is silently accepted as absent.
The parser rejects invalid JSON shapes, but generator-side public guardrails do
not.

## Existing Behavior Confirmed

- Nested select recursion and default `$this` wrappers execute with matching
  native/fallback results.
- Parent columns combine with child select rows as expected.
- Empty nested selects with parent columns preserve the parent output schema and
  rows.
- Nested child `forEach` under an enclosing `forEachOrNull` keeps inner row-set
  semantics, matching the existing spec fixture behavior.
