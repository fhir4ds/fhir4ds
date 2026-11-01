# Code Review Findings

Scope: SPEC COMPLIANCE MILESTONE REVIEW after 30 completed chunks. Reviewed CQL-06 through CQL-10 archived handoffs and the touched CQL translator, Python UDF/macro, and native CQL extension surfaces. This was review-only: no remediation was implemented, no new spec chunk was initialized, no files were archived, and `spec_schedule.json` was not modified.

## New Findings From Review-30

### REV-030-001 - HIGH - `ext()` builds injectable FHIRPath predicates from unescaped CQL strings

Evidence: [fhir4ds/cql/translator/expressions/_functions.py](/mnt/d/fhir4ds/fhir4ds/cql/translator/expressions/_functions.py:1098) lowers bare `ext(element, url)` by interpolating `url_val` directly into `extension.where(url='{url_val}')`. The resulting string is then passed to `fhirpath_text` as a FHIRPath expression, so a CQL string containing an escaped quote can change the predicate.

Fresh review probe:

```text
define E: ext(Patient, 'http://evil.example/a\' or true or url=\'b')
```

translated to:

```sql
fhirpath_text(_pt.patient_resource, 'extension.where(url=''http://evil.example/a'' or true or url=''b'')')
```

Executing the injected FHIRPath against a Patient with an unrelated extension returned the unrelated extension value (`leaked`) instead of no match.

Recommended next action: build the predicate with a FHIRPath string-literal escaping helper or avoid predicate string construction entirely by using a structured extension lookup helper. Add regression coverage for URLs containing single quotes, backslashes, and FHIRPath operators.

### REV-030-002 - HIGH - Decimal `HighBoundary` / `LowBoundary` mishandle negative values and coarser precision

Evidence: Python fallback [fhir4ds/cql/duckdb/udf/math.py](/mnt/d/fhir4ds/fhir4ds/cql/duckdb/udf/math.py:580) and native/browser [extensions/cql/src/cql/boundary.cpp](/mnt/d/fhir4ds/extensions/cql/src/cql/boundary.cpp:637) implement Decimal boundaries by appending `9` or `0` characters. That works for positive default precision only. It ignores requested precision when it is coarser than the input scale and reverses the numeric direction for negative values.

Fresh review probes:

```text
SELECT LowBoundary('-1.587')  -> -1.58700000
SELECT HighBoundary('-1.587') -> -1.58799999
```

`HighBoundary` is numerically lower than `LowBoundary`, violating the CQL definition that high is the greatest possible value and low is the least possible value. Coarser precision is also ignored:

```text
SELECT LowBoundary(1.587, 2)  -> 1.587
SELECT HighBoundary(1.587, 2) -> 1.587
```

The same behavior reproduced in the no-Python/browser-style C++ runtime. The official CQL reference defines Decimal boundary overloads with an explicit precision parameter and gives `HighBoundary(1.587, 8) -> 1.58799999` and `LowBoundary(1.587, 8) -> 1.58700000` as examples.

Recommended next action: replace string-append boundary construction with Decimal arithmetic/quantization that handles sign and requested precision. Add Python fallback, native-loaded, translated CQL, and no-Python C++ tests for positive coarser precision and negative decimals.

## Carried-Forward Open Findings

### REV-001 - HIGH - Native FHIRPath Section 5.1 arity validation remains incomplete

Carried from review-25. Native `evalFunction` still lacks exact arity guards for collection helpers such as `exists`, `all`, `subsetOf`, `supersetOf`, `count`, `empty`, `distinct`, `isDistinct`, `hasValue`, and Boolean aggregates. Add exact signature checks before native semantic dispatch and keep native/fallback parity tests together.

### REV-002 - MEDIUM - Native `fhirpath_timestamp` still accepts invalid resource-backed DateTime strings

Carried from review-25. Native wrapper validation still checks shape before returning resource-backed timestamp strings. Route through the strict DateTime parser or enforce identical range rules.

### REV-003 - MEDIUM - `fhirpath_quantity` typed wrappers accept malformed Quantity objects

Carried from review-25. Native and fallback typed wrappers still accept Quantity-like objects by shape rather than requiring finite JSON-numeric `value` and string `unit`/`code`.

### REV-004 - MEDIUM - Native Unicode `upper()` / `lower()` still use incomplete local case tables

Carried from review-25. Replace hand-maintained native case mappings with generated Unicode data or a Unicode-aware library path, then parity-test one-to-one and one-to-many mappings.

### REV-005 - MEDIUM - FHIR model/type knowledge remains embedded in generic FHIRPath runtime code

Carried from review-25. Native FHIRPath still embeds field primitive metadata and type hierarchy logic that should come from generated/shared model metadata.

### REV-006 - MEDIUM - FHIRPath string/STU helper arity validation remains incomplete

Carried from review-25. Add exact signatures for `trim`, `split`, `join`, `matchesFull`, `escape`, `unescape`, `encode`, and `decode`; public result UDFs can stay row-resilient while `fhirpath_is_valid()` rejects malformed calls.

### REV-007 - HIGH - Qualified ValueSet references from included CQL libraries lower to missing CTEs

Carried from review-25. Resolve `Lib.ValueSetName` through included terminology symbols or raise a clear translation error instead of synthesizing `SELECT * FROM "Lib.ValueSetName"`.

### REV-008 - HIGH - Generic CQL ValueSet membership embeds QICore-specific behavior

Carried from review-25. Move `qicore-notDoneValueSet` behavior out of generic Python/native terminology membership and behind a profile/IG adapter or registry-driven configuration.

## Closed Since Review-25

- Review-25 `REV-009` is closed by CQL-06 SKEPTIC: conversion macro private-function registration no longer swallows arbitrary unexpected exceptions.

## Review Notes

Fresh probes were limited to review evidence for the two new findings. Full conformance was not rerun in this review pass; CQL-10 EXPLORER reported full conformance `2822/2822` before the milestone review.
