# CQL-05 SKEPTIC QA Handoff

## Scope

- Chunk: CQL-05, Type Operators - Structural.
- Items tested: `As<T>(argument)`, `Children(argument)`, `Convert to<T>(argument)`, `Descendants(argument)`, `Is<T>(argument)`.
- Backend discipline: fresh probes against translated CQL, native-loaded DuckDB registration, and forced Python fallback registration. No archived `spec_comp/**` artifacts were used as evidence.

## Findings

1. Structural `is`/`as` validation did not consistently reject unknown type targets.
2. `List<T>` and `Interval<T>` type specifiers were not handled as first-class structural targets.
3. Static structural inference missed aliases, Ratio values, and exact temporal type boundaries.
4. `as Quantity` lost Quantity shape in population SQL and broke downstream unit-aware comparisons.
5. `Message(..., 'Error', ...) as Interval<T>` leaked strict-error behavior in DQM measure SQL.
6. Dynamic FHIR `as Concept`/`as Code` erased runtime CodeableConcept/Coding values before terminology equivalence.
7. Function-inlined `ParameterPlaceholder` property navigation did not accept SQL CASE sources created by choice `as` casts.
8. Scalar quantity comparison fallback initially regressed CMS0334 by allowing `37 cm >= 37 weeks`; fallback is now blocked for JSON Quantity objects.

## Verification

- Focused structural/native-vs-forced-fallback pytest: 8 passed.
- Targeted DQM subset for previously regressed measures: 12/12 perfect.
- Broad CQL pytest: 4913 passed, 5 skipped.
- Full conformance: ViewDefinition 134/134, FHIRPath R4 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
- `git diff --check`: clean.
