# QA Handoff - FP-04 SKEPTIC

Phase: QA
Iteration: 1
Personality: SKEPTIC
Spec focus: FHIRPath §5.2 Filtering and Projection
Spec source: https://hl7.org/fhirpath/N1/#filtering-and-projection

## Hypotheses Probed

- `where(criteria)` may leak `$index` or variables, or may accept non-Boolean criteria.
- `select(projection)` may fail to flatten projection collections or may leak callback variables.
- `repeat(projection)` may include seed input, mishandle `$index`, or de-duplicate with non-semantic equality.
- `ofType(type)` may mishandle FHIR supertypes, exact FHIR primitive behavior, or invalid type specifiers.
- Native C++ and forced Python fallback may diverge on public row-resilient errors.

## Result

Found 1 MEDIUM issue:

- `QA-001`: native `fhirpath_is_valid()` can return `true` for `ofType(<unknown>)` when the validation sample makes the source path empty. The spec says the `ofType` type argument must resolve to a model type. Forced Python fallback returns `false`; native should validate the type specifier before empty-input short-circuiting.

Probe artifacts:

- `.temp/qa/fp04_skeptic_probe.py`
- `.temp/qa/fp04_skeptic_probe.log`

Non-issues verified during the fresh probe:

- `where(criteria)` enforces singleton Boolean criteria and restores `$index`.
- `select(projection)` flattens multi-item projection results.
- `repeat(projection)` returns projection results only, scopes `$index`, and preserves duplicate downstream scalar values when projected complex items are not semantically equal.
- `ofType(DomainResource)`, `ofType(Patient)`, and exact FHIR primitive `ofType(code)` behavior matched across native and forced fallback.
