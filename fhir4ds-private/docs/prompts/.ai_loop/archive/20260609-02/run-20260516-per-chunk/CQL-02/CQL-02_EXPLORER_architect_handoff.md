# Architect Handoff - CQL-02 EXPLORER

Iteration: 1
Audit status: PASS

## Golden Standard

Golden standard written to `.temp/architect/golden_standard.md`. The key invariant for this pass is that CQL clinical values remain CQL clinical values in value/type contexts, while terminology boundaries unwrap only where required. Code/Concept equivalence must follow CQL clinical semantics, and clinical metadata must propagate through aliases instead of falling through to FHIR resource checks.

## Structural Audit

No new architecture findings.

The remediation is structurally aligned with the translator design:

- It preserves the SQL AST pipeline and does not introduce new raw SQL templates.
- It keeps terminology semantics in the expression translation layer and FHIRPath predicate construction in `fhirpath_builder`.
- It does not add measure-specific, valueset-specific, or implementation-guide-specific branches.
- The `build_multi_coding_exists_expr(..., is_coding_type=False)` extension is backward compatible and keeps Coding-vs-CodeableConcept path handling centralized.
- Native-loaded and forced Python fallback execution are covered in regression tests where DuckDB-backed behavior is involved.

## QA Audit

QA was sufficient for the EXPLORER role. It covered weird compositions and cross-boundary cases: Code/Concept equivalence, dynamic FHIR CodeableConcept comparison, query `let`/`return` aliases, ValueSet/Vocabulary metadata propagation, DQM fluent ValueSet normalization inherited from the previous pass, and native/fallback DuckDB parity. No `RETRY_QA` veto.

## Issue Summary

- `CQL02-EXPLORER-001`: RESOLVED
- `CQL02-EXPLORER-002`: RESOLVED

Recommended fix order: none; all active issues are terminal.

## Validation

- Focused clinical parity: 11/11 passed
- Official CQL conformance: 1706/1706 passed
- Broad CQL pytest: 515 passed, 5 skipped
- Full conformance: 2822/2822 passed
