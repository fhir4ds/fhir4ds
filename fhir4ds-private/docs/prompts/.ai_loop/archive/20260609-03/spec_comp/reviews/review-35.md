# Code Review Findings

Scope: SPEC COMPLIANCE MILESTONE REVIEW after 35 completed chunks. Reviewed archived handoffs for CQL-11 through CQL-15 and targeted the touched CQL translator, Python UDF/macro, and native CQL extension interval/date-time/arithmetic/string surfaces. This was review-only: no remediation was implemented, no new chunk was initialized, no files were archived, and `spec_schedule.json` was not modified.

## New Findings From Review-35

### REV-035-001 - HIGH - Direct `expand` accepts malformed non-null `per` as default

Evidence: [interval.py](/mnt/d/fhir4ds/fhir4ds/cql/duckdb/udf/interval.py:2733) parses `per` only when it is JSON starting with `{`; parse failures are swallowed and the function returns `(None, None)`, which is the same signal as an omitted `per`. The expansion paths then consume that default at [interval.py](/mnt/d/fhir4ds/fhir4ds/cql/duckdb/udf/interval.py:2855) and [interval.py](/mnt/d/fhir4ds/fhir4ds/cql/duckdb/udf/interval.py:2891). The no-Python C++ path has the same shape: [cql_extension.cpp](/mnt/d/fhir4ds/extensions/cql/src/cql_extension.cpp:1766) returns a default `ExpandStep` when `parse_quantity_json(per)` fails, so `step.supplied` remains false.

Fresh review probe from the active findings file:

```text
SELECT expand_points(intervalFromBounds('1','3',true,true), 'bad')
```

Actual behavior:

```text
forced Python -> [1,2,3]
no-Python C++ -> [1,2,3]
```

Expected behavior: malformed non-null `per` is not a compatible Quantity and must not silently default. The row-resilient public surface should return SQL NULL or an empty expansion consistently, while an omitted or null `per` may use the CQL default.

Why this matters: CQL-15 EXPLORER correctly tightened incompatible `per` semantics when `per` parses as a Quantity, but malformed non-null strings still bypass the compatibility checks because the parser erases the distinction between malformed and absent input.

Recommended next action: make Python and C++ `per` parsers return three states: omitted/null, parsed Quantity, and malformed non-null. Add direct forced Python, native-loaded, and no-Python/browser-style tests for malformed `per`, null `per`, valid numeric default-unit `per`, valid temporal `per`, valid Quantity `per`, and incompatible units.

## Carried-Forward Open Findings

### REV-001 - HIGH - Native FHIRPath Section 5.1 arity validation remains incomplete

Carried from review-25. Native `evalFunction` still lacks exact arity guards for collection helpers such as `exists`, `all`, `subsetOf`, `supersetOf`, `count`, `empty`, `distinct`, `isDistinct`, `hasValue`, and Boolean aggregates.

### REV-002 - MEDIUM - Native `fhirpath_timestamp` still accepts invalid resource-backed DateTime strings

Carried from review-25. Native wrapper validation still checks shape before returning resource-backed timestamp strings. Route through the strict DateTime parser or enforce identical range rules.

### REV-003 - MEDIUM - `fhirpath_quantity` typed wrappers accept malformed Quantity objects

Carried from review-25. Native and fallback typed wrappers still accept Quantity-like objects by shape rather than requiring finite JSON-numeric `value` and string `unit` or `code`.

### REV-004 - MEDIUM - Native Unicode `upper()` / `lower()` still use incomplete local case tables

Carried from review-25. Replace hand-maintained native case mappings with generated Unicode data or a Unicode-aware library path, then parity-test one-to-one and one-to-many mappings.

### REV-005 - MEDIUM - FHIR model/type knowledge remains embedded in generic FHIRPath runtime code

Carried from review-25. Native FHIRPath still embeds field primitive metadata and type hierarchy logic that should come from generated/shared model metadata.

### REV-006 - MEDIUM - FHIRPath string/STU helper arity validation remains incomplete

Carried from review-25. Add exact signatures for `trim`, `split`, `join`, `matchesFull`, `escape`, `unescape`, `encode`, and `decode`.

### REV-007 - HIGH - Qualified ValueSet references from included CQL libraries lower to missing CTEs

Carried from review-25. Resolve `Lib.ValueSetName` through included terminology symbols or raise a clear translation error instead of synthesizing `SELECT * FROM "Lib.ValueSetName"`.

### REV-008 - HIGH - Generic CQL ValueSet membership embeds QICore-specific behavior

Carried from review-25. Move `qicore-notDoneValueSet` behavior out of generic Python/native terminology membership and behind a profile/IG adapter or registry-driven configuration.

### REV-030-002 - HIGH - Decimal `HighBoundary` / `LowBoundary` mishandle negative values and coarser precision

Carried from review-30. The issue remains open: Decimal boundary helpers still need sign-aware arithmetic/quantization for negative values and requested precision lower than the authored scale, with parity coverage across translated SQL, Python fallback, native-loaded, and no-Python extension surfaces.

## Closed Since Review-30

- `REV-030-001` is closed by CQL-12 EXPLORER: generated FHIRPath string predicates, including `ext(element, url)`, now use `escape_fhirpath_string_literal()` before constructing predicate strings.
- Review-25 `REV-009` remains closed by CQL-06 SKEPTIC: conversion macro private-function registration no longer swallows arbitrary unexpected exceptions.

## Process Notes

- Quarantined premature CQL-16 SKEPTIC artifacts exist under `spec_comp/misfires/1780247987_cql16_skeptic_during_cql15_historian/`, plus `.temp/qa/cql16_explorer_probe.py`. They are process-risk context only and were not treated as accepted CQL-16 evidence.
- Full conformance was not rerun as part of this read-only review. CQL-15 EXPLORER reported full conformance `2822/2822` after the final CQL-15 fixes.
