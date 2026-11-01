# Architect Handoff: SOF-VD-06 HISTORIAN

## Structural Health

The SOF-VD-06 iterator surface is structurally healthier after this pass. Parser/type validation now matches the SQL-on-FHIR logical-model constraint before SQL generation, and iterator context routing is centralized in `SQLGenerator._resolve_environment_path_context()` for `%context`, `%resource`, and `%rootResource`.

## Golden Standard Audit

Golden standard recorded in `.temp/architect/golden_standard.md`. The relevant invariants are now satisfied:

- Parser and public constructors enforce logical-model shape before SQL generation.
- `forEach`/`forEachOrNull` establish the current item for ordinary paths and `%context`.
- `%resource`/`%rootResource` route to the root resource, including function/predicate tails.
- `%rowIndex` stays ordinality-backed and backend-neutral.
- Mixed root/current built-in expressions do not silently evaluate against the wrong single JSON input.

## Issue Summary

- Total issues: 2
- Resolved: 2
- Open: 0
- New architecture findings: 0
- QA retry: not required

## QA/Engineer Compression

HISTORIAN verified the spec boundaries for `forEach`/`forEachOrNull` and found two real regressions: iterator mutual exclusion with `repeat` was not enforced by parser/public validation, and non-trivial leading `%resource.*` expressions under iterators were evaluated against the current unnested alias. Engineering fixed both with focused parser/generator changes and regression tests, then validated native-loaded and forced Python fallback DuckDB execution plus full conformance and pytest gates.

## Recommended Fix Order

No further engineer phase is recommended for this chunk. Future work should treat true mixed-context FHIRPath expressions as requiring a multi-input evaluator surface rather than ad hoc string rewriting.
