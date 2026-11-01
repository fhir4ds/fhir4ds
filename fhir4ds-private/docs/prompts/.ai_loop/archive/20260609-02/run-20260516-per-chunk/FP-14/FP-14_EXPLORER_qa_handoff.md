# QA Handoff - FP-14 EXPLORER

## Scope

Fresh run for FHIRPath §6.2 comparison operators: `>`, `<`, `<=`, `>=`.
Validated against the HL7 FHIRPath normative comparison text: operands must be
the same type or implicitly convertible; integers may compare with decimals;
strings compare lexicographically; quantity conversion may be supported; partial
temporal precision mismatches return empty.

## Probe

Created `.temp/qa/fp14_explorer_fresh/probe_fp14_comparison.py` and ran native
C++ DuckDB and forced Python fallback in separate Python processes to avoid
DuckDB extension registration cross-contamination.

Covered:
- integer/decimal comparisons
- string lexicographic comparisons and string-vs-number incompatibility
- Boolean ordering
- quantity literal conversion and incompatible units
- Date, DateTime, Time precision behavior
- null and multi-item operands
- JSON scalar path values
- FHIR Quantity path comparisons using choice paths and explicit paths

## Finding

`QA-001` HIGH: forced Python fallback fails display-unit-only FHIR Quantity path
comparison while native C++ compares it.

Reproducer:

```python
resource = {
    "resourceType": "Observation",
    "valueQuantity": {"value": 4, "unit": "m"},
    "component": [{"valueQuantity": {"value": 4, "unit": "cm"}}],
}
expression = "valueQuantity > component.valueQuantity"
```

Observed:
- Native C++ DuckDB: `(['true'], '[true]', True, 'true')`
- Forced Python fallback: `([], None, None, None)`

Likely cause:
`fhir4ds/fhirpath/engine/util.py::parse_value()` only materializes dict
Quantities when `code` is present, while native C++ recognizes structural
Quantity objects using `code` or `unit`.

## Validation Run

- `python3 .temp/qa/fp14_explorer_fresh/probe_fp14_comparison.py` failed only on `QA-001`.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py -q` passed: 3 tests.

