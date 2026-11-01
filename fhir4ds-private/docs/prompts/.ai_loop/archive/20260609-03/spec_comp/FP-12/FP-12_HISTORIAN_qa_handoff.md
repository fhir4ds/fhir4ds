# QA Handoff — FP-12 HISTORIAN

## Scope

FHIRPath Normative Release §5.8 tree navigation and §5.9 utility functions:
`children()`, `descendants()`, `trace(name, [projection])`, `now()`,
`timeOfDay()`, and `today()`.

Spec grounding:
- §5.8.1 says `children()` returns all immediate child nodes.
- §5.8.2 says `descendants()` returns all descendant nodes, excludes the input
  nodes themselves, and is shorthand for `repeat(children())`.
- §5.9.1 says `trace(name : String [, projection])` returns the input
  unchanged; if projection is present, that projection is evaluated on the
  trace input for logging.
- §5.9.2 says current clock functions must return stable values within a
  single expression.
- FHIR R4 §2.9.1 says FHIRPath is evaluated over the FHIR logical model, not
  JSON/XML representation details such as split primitive fields.

## Probe

Fresh probe written to `.temp/qa/fp12_historian_probe.py` and run against both
the native C++ DuckDB extension and forced Python fallback. It covered:
- Null child preservation in `children()` and `fhirpath_json`.
- Recursive `descendants()` count, shape, and `repeat(children())` equivalence.
- Primitive input, empty input, and multi-item input for tree functions.
- `trace` identity, invalid signatures, projection evaluation, projection
  error row resilience, empty input, and dynamic name argument behavior.
- `now()`, `today()`, `timeOfDay()` type, string shape, and same-expression
  determinism.
- Invalid arity for every FP-12 function.

## Findings

`QA-001` MEDIUM: forced Python fallback `descendants()` exposes
primitive-extension underscore JSON containers. The fallback returned
`midday` from `_birthDate.extension.valueString` as a descendant even though
`children()` skips the split JSON representation and native traversal did not
expose it.

`QA-002` MEDIUM: native `trace(name, projection)` evaluates the `name` argument
against the traced source collection. `name.trace(id).given.count()` returns
empty natively but returns the unchanged input in fallback. The optional
projection is the argument that §5.9.1 evaluates over the trace input.

## Validation

Initial probe produced the two findings above. No source files were modified
during QA.
