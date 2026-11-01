# QA Handoff - FP-05 EXPLORER

## Scope
FHIRPath §5.3 Subsetting and §5.4 Combining: `[index]`, `single()`, `first()`, `last()`, `tail()`, `skip(num)`, `take(num)`, `intersect(other)`, `exclude(other)`, `union(other)`, and `combine(other)`.

## Spec Basis
Verified against the HL7 FHIRPath specification text for §5.3 and §5.4. Relevant requirements:
- `[index]` is 0-based and out-of-range/empty input returns empty.
- `single()` returns the item for one input, empty for empty input, and signals an evaluation error for multiple items.
- `skip(num <= 0)` returns the input collection; `take(num <= 0)` returns empty.
- `intersect()` eliminates duplicates; `exclude()` preserves duplicates not present in `other`.
- `union()` eliminates duplicates using FHIRPath `=` equality; `combine()` keeps duplicates.

## Exploration Performed
- Compared native DuckDB extension UDFs (`register_fhirpath()` loaded C++) against Python fallback UDF functions for scalar, JSON, Boolean, and collection outputs.
- Exercised negative/out-of-range indexers, empty and multi-item arguments, strict `single()`, `skip()`/`take()` boundaries, set-style operations over strings, objects with reordered keys, compatible numeric values, and duplicate-preserving operations.
- Probed direct public Python collection helpers for subsetting boundary behavior.

## Issues Found
1. `QA-001` HIGH: Native C++ `union()`, `intersect()`, and `exclude()` do not treat JSON integer `1` and JSON real `1.0` as equal, even though direct `int = real` returns true. This violates equality-backed set semantics and diverges from Python fallback.
2. `QA-002` MEDIUM: `FHIRPathCollection.take(-1)` returns `[1, 2]` and `FHIRPathCollection.skip(-1)` returns `[3]` through raw Python slicing. Spec requires `take(num <= 0)` to return empty and `skip(num <= 0)` to return the input.

## Reproducers
```python
resource = '{"resourceType":"Observation","int":[1],"real":[1.0]}'
# Native C++: ["2"], Python fallback: ["1"]
fhirpath(resource, "int.union(real).count()")
# Native C++: ["0"], Python fallback: ["1"]
fhirpath(resource, "int.intersect(real).count()")
# Native C++: ["1"], Python fallback: ["0"]
fhirpath(resource, "int.exclude(real).count()")
```

```python
FHIRPathCollection([1, 2, 3]).take(-1).values  # actual [1, 2], expected []
FHIRPathCollection([1, 2, 3]).skip(-1).values  # actual [3], expected [1, 2, 3]
```

## State
`evolution.json` has two open issues and phase is set to `FIX`.

## Final QA Exit Check
After remediation and architecture audit, `evolution.json` contains only verified tombstones and no non-terminal CRITICAL/HIGH/MEDIUM issues. A final focused regression check passed:

```bash
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py::test_set_operators_use_numeric_equality_for_json_ints_and_reals fhir4ds/fhirpath/duckdb/tests/unit/test_filter.py::TestTake::test_take_negative fhir4ds/fhirpath/duckdb/tests/unit/test_filter.py::TestSkip::test_skip_negative -q
# 3 passed
```
