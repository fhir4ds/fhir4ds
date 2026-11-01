# QA Handoff - FP-14 HISTORIAN

## Scope

- Chunk: FP-14
- Spec: FHIRPath Normative Release v2.0.0, Section 6.2 Comparison
- Operators: `>`, `<`, `<=`, `>=`
- Personality: HISTORIAN

## Spec Oracle

Section 6.2 defines comparison operators over singleton operands of the same type, or operands convertible through implicit conversion. The section examples explicitly cover Integer-to-Decimal comparison, lexicographic String comparison, UCUM-compatible Quantity comparison such as `4 'm' > 4 'cm'`, and empty results for temporal comparisons with insufficient/different precision.

The normative page's prose defines `<=` and `>=` correctly; some example comments on that page appear copy-swapped for simple numeric/string cases, so the probe used the operator definition and temporal precision rules as the oracle.

## Probes Run

Tested native DuckDB C++ extension and forced Python fallback with:

- Numeric Integer/Decimal comparisons for all four operators.
- String lexicographic comparisons, including numeric-looking strings and String-vs-Number incompatibility.
- Boolean ordering (`false < true`, `true > false`).
- Quantity literals with compatible and incompatible UCUM units.
- Date, DateTime, and Time literals at same and different precision, including timezone-normalized DateTime comparisons.
- Empty and multi-item operands.
- Valid FHIR JSON Quantity fields on `Observation.valueQuantity` and `Observation.component.valueQuantity`.

## Finding

`QA-001` is open. Native C++ returns empty/NULL for comparison between two FHIR JSON Quantity path operands, while the forced Python fallback returns the spec-compliant UCUM comparison result.

Reproducer:

```sql
SELECT
  fhirpath_bool(resource, 'value > component.value'),
  fhirpath_json(resource, 'value > component.value')
FROM (SELECT '{"resourceType":"Observation","valueQuantity":{"value":4,"unit":"m","code":"m","system":"http://unitsofmeasure.org"},"component":[{"valueQuantity":{"value":4,"unit":"cm","code":"cm","system":"http://unitsofmeasure.org"}}]}'::JSON AS resource);
```

Native result: `NULL`, `NULL`

Forced Python fallback result: `true`, `[true]`

Literal quantity comparisons, for example `4 'm' > 4 'cm'`, pass in both paths, so the failure is isolated to native JSON Quantity path materialization before comparison.
