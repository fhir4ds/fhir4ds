# CQL-07 Iteration 1 — Engineer Handoff (Remediation)

**Chunk**: CQL Type Operators - Conversions
**Issues Addressed**: FUZZ-007 (MEDIUM, DATA_HANDLING)
**Date**: 2026-07-01

## Triage

| Issue | Severity | Category | Triage |
| :--- | :--- | :--- | :--- |
| FUZZ-007 | MEDIUM | DATA_HANDLING | CONFIRMED — reproducer verified, spec-cited, surgical fix applied. |

## FUZZ-007 — Surgical Fix

### Root Cause

In `fhir4ds/cql/duckdb/udf/conversion.py:ToRatio`, the JSON-object input branch
fell through to `json.dumps(data)` directly without normalizing the
numerator/denominator quantities. The text-input branch (via
`_parse_ratio_text`) calls `toQuantity` on each side, which produces canonical
JSON containing `value`/`unit`/`code`/`system` keys via `_format_cql_quantity`.
The JSON-input branch produced non-canonical output that lacked `code`/`system`
fields, breaking the ToString(ToRatio(x)) round-trip invariant.

### Spec Reference

CQL v1.5.3 §22.32 ToRatio — the operator's normative contract is String-input
only (`<quantity>:<quantity>`). JSON-object Ratio input is a beyond-spec
extension. The fix preserves the extension but eliminates the internal
inconsistency by routing both input forms through the same canonicalizer.

### Surgical Change

`fhir4ds/cql/duckdb/udf/conversion.py`:

1. Imported `_format_cql_quantity` from `..udf.quantity`.
2. Added private helper `_normalize_quantity_object(value)` that:
   - Accepts dict or JSON-string-encoded dict.
   - Validates via `is_valid_quantity_object`.
   - Renders through `_format_cql_quantity(value, unit)` to produce canonical
     `value`/`unit`/`code`/`system` keys.
   - Returns None when the input is not a valid Quantity.
3. Modified `ToRatio` JSON-input branch to call `_normalize_quantity_object` on
   numerator and denominator before serializing.

Net change: ~25 lines added; no other call sites touched.

### Validation

Reproducer passes (text and JSON inputs now produce structurally identical
canonical Ratio JSON with `code`/`system` keys).

Full conformance suite:

```
ViewDefinition            | 134      | 134      |  100.0%
FHIRPath (R4)             | 935      | 935      |  100.0%
CQL                       | 1706     | 1706     |  100.0%
DQM (QI Core 2025)        | 47       | 47       |  100.0%
OVERALL COMPLIANCE        | 2822     | 2822     |  100.0%
```

**Zero regressions.** Baseline matches `PROC_VALIDATION.md`.

## Terminal Status

- FUZZ-007: `RESOLVED` — fix applied, reproducer passes, baseline preserved.
