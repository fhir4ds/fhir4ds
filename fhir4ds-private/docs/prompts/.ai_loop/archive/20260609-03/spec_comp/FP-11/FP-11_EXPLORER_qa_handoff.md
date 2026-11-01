# QA Handoff — FP-11 EXPLORER

## Scope

- Chunk: FP-11, FHIRPath §5.7 Math (STU)
- Personality: EXPLORER
- Spec source: HL7 FHIRPath Normative Release §5.7.1-§5.7.10, especially §5.7.8 `round([precision : Integer]) : Decimal`
- Probe: `.temp/qa/fp11_explorer_probe.py`

## Strategy

EXPLORER stress cases covered chained math, domain-empty results, overflow-empty behavior, dynamic sibling arguments, optional empty arguments, literal-union singleton edges, invalid arity/type inputs, resource-backed non-numeric inputs, and native C++ vs forced Python fallback parity.

## Finding

`QA-001` — MEDIUM, SPEC_VIOLATION

Native C++ `round()` leaks binary floating-point artifacts when the requested precision exceeds the authored Decimal precision.

Reproducer:

```sql
SELECT
  fhirpath_text('{}'::JSON, '1.23456789.round(20)'),
  fhirpath_json('{}'::JSON, '1.23456789.round(20)'),
  fhirpath_is_valid('1.23456789.round(20)');
```

Actual native:

```text
text = 1.23456788999999989009
json = [1.23456788999999989009]
valid = true
```

Forced Python fallback:

```text
text = 1.23456789
json = [1.23456789]
valid = true
```

Expected: `round([precision])` returns `Decimal`, and the precision argument selects the decimal place for rounding. With a precision beyond the input scale, `1.23456789.round(20)` should remain `1.23456789`, not expose binary double representation.

## Validation

Fresh probe before remediation:

```text
case_count = 56
mismatch_count = 1
expectation_failure_count = 2
```

