# QA Handoff - FP-15 EXPLORER

## Scope
- Chunk: FP-15
- Spec: FHIRPath §6.3 Types
- Items: `is type specifier`, `is(type)`, `as type specifier`, `as(type)`
- Personality: EXPLORER

## Spec Basis
FHIRPath N1 §6.3.1-§6.3.4 says `is` and `as` use a right-hand type specifier that must resolve to a model type. `is` returns true for the input type or subclass, false for a non-match, errors on unresolved type names and multi-item inputs, and returns empty for empty input. `as` returns the original singleton input for the requested type or subclass, errors on unresolved type names and multi-item inputs, and otherwise returns empty. Function forms are backwards-compatible aliases whose argument must be treated as a type specifier, not a runtime expression.

## Exploration
Created and ran `.temp/qa/fp15_explorer_probe.py` against the in-worktree package. The corrected probe executes native/C++ DuckDB and forced Python fallback in isolated subprocesses and compares 39 surfaces across:
- operator and function forms for System literals
- FHIR primitive `is()` subtype behavior vs exact `as()` behavior
- resource and complex supertypes (`Resource`, `DomainResource`, `Element`)
- contained-resource filters with `$this is Type` and `$this.is(Type)`
- qualified and backtick type specifiers
- `System.Patient` valid-but-nonmatching behavior
- runtime field names passed as type arguments
- empty input and multi-item singleton boundaries
- unknown types, wrong arity, and invalid model namespaces

Result: `OK 39 cases`, no native/fallback mismatches.

## Validation
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py -q --tb=short` -> 17 passed.
- `extensions/fhirpath/build/release/test/unittest '*fhirpath*'` -> 250 assertions passed in 2 test cases.
- `python3 conformance/scripts/run_all.py` summary -> ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, OVERALL 2822/2822.

## Issues
No new issues opened.

## Files Updated
- `fhir4ds/fhirpath/AGENTS.md`
- `extensions/fhirpath/AGENTS.md`
