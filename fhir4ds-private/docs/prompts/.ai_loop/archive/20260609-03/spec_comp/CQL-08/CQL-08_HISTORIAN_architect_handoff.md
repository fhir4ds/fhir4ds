# Architect Handoff: CQL-08 HISTORIAN

## Golden Standard

Wrote `.temp/architect/golden_standard.md` with nullological invariants for
`Coalesce`, `IsNull`, `IsTrue`, and `IsFalse`.

## Audit Summary

No architectural findings were logged. The current nullological implementation
preserves the relevant boundaries:

- CQL scalar `Coalesce` arity validation is separate from the single-list
  overload.
- Literal-list, query-produced-list, and scalar list-valued `Coalesce` cases
  are covered by fresh probes and focused parity tests.
- `IsTrue` and `IsFalse` use Boolean-exact semantics rather than DuckDB SQL
  truthiness.
- Dynamic FHIR Boolean tests use `fhirpath_bool`, while null checks correctly
  see missing paths as SQL NULL.
- Native-loaded and forced Python fallback registrations matched.

## QA Enforcer Gate

QA was sufficient for this HISTORIAN pass. It walked the official XML examples,
the official CQL reference signatures, prior CQL-08 SKEPTIC fixes, public
DuckDB helper calls, typed structured values, query-produced lists, and dynamic
FHIR Boolean population SQL. `RETRY_QA` is not needed.

## Validation

- Fresh probe passed.
- Focused nullological parity passed 8/8.
- Official nullological compliance passed 22/22.
- Full conformance passed 2822/2822.

## Recommended Fix Order

No fixes are required. Proceed to clean exit for this inner loop.
