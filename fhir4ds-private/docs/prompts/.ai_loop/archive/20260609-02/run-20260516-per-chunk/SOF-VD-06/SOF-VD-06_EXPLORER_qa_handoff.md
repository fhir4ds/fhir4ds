# QA Handoff: SOF-VD-06 EXPLORER

Personality: EXPLORER
Iteration: 1
Scope: SQL-on-FHIR ViewDefinition `select.forEach` and `select.forEachOrNull`.

## Spec Anchors

- SQL-on-FHIR ViewDefinition definitions say `forEach` produces one row per selected element, and `forEachOrNull` preserves one row with null nested values when the collection is empty.
- SQL-on-FHIR environment-variable behavior says built-in variables can be referenced in FHIRPath expressions and `%rowIndex` is the 0-based index inside `forEach`, `forEachOrNull`, and `repeat`.
- FHIRPath defines `%resource` as the resource containing the original `%context` node and `%rootResource` as that resource's containing root.

## Probes

- Created fresh QA probes under `.temp/qa/` without using archived workflow outputs as evidence.
- Compared native C++ DuckDB registration (`register_fhirpath(...) is True`) and forced Python fallback registration.
- Exercised standalone `%rowIndex`, `%rowIndex` embedded in a column expression, `%rowIndex` embedded in select `where`, nested `forEachOrNull`, `%context`, `%resource`, and `%rootResource`.

## Findings

- `QA-001` HIGH OPEN: expression-level `%rowIndex` is not propagated into DuckDB FHIRPath calls. Standalone `%rowIndex` columns work, but `iif(%rowIndex = 0, ...)` returns NULL and select `where` path `%rowIndex = 1` returns no rows with undefined-variable diagnostics. Native C++ registration and forced Python fallback match the broken behavior.

## Recommended Fix

Thread the active row-index SQL expression through generator column, where, and nested iterator path generation. When `%rowIndex` occurs outside FHIRPath string literals/comments, build the FHIRPath expression argument dynamically so the DuckDB UDF receives a concrete numeric literal for the current row.
