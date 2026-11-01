# Code Review Findings

Scope: SPEC COMPLIANCE MILESTONE REVIEW after 40 completed chunks. Reviewed
archived CQL-16 through CQL-20 handoffs and the touched CQL translator,
macro/UDF, native CQL extension, and aggregate/list/interval parity tests. This
was review-only: no remediation was implemented and `spec_schedule.json` was
not modified.

## New Findings From Review-40

No new findings.

The CQL-20 EXPLORER changes are structurally consistent with the CQL translator
boundary: query-form `Product` is disambiguated with `system.product`, static
aggregate validation is AST/type based, and dynamic FHIR-derived values remain
on runtime-checked paths rather than being classified from SQL transport shape.
The added tests cover translated CQL, direct public helper surfaces, and
forced Python/native/no-Python parity.

## Carried-Forward Open Findings

### REV-001 - HIGH - Native FHIRPath Section 5.1 arity validation remains incomplete

Carried from review-25. Native `evalFunction` still lacks exact arity guards
for collection helpers such as `exists`, `all`, `subsetOf`, `supersetOf`,
`count`, `empty`, `distinct`, `isDistinct`, `hasValue`, and Boolean aggregates.

### REV-002 - MEDIUM - Native `fhirpath_timestamp` still accepts invalid resource-backed DateTime strings

Carried from review-25. Native wrapper validation still checks shape before
returning resource-backed timestamp strings. Route through the strict DateTime
parser or enforce identical range rules.

### REV-003 - MEDIUM - `fhirpath_quantity` typed wrappers accept malformed Quantity objects

Carried from review-25. Native and fallback typed wrappers still accept
Quantity-like objects by shape rather than requiring finite JSON-numeric
`value` and string `unit` or `code`.

### REV-004 - MEDIUM - Native Unicode `upper()` / `lower()` still use incomplete local case tables

Carried from review-25. Replace hand-maintained native case mappings with
generated Unicode data or a Unicode-aware library path, then parity-test
one-to-one and one-to-many mappings.

### REV-005 - MEDIUM - FHIR model/type knowledge remains embedded in generic FHIRPath runtime code

Carried from review-25. Native FHIRPath still embeds field primitive metadata
and type hierarchy logic that should come from generated/shared model metadata.

### REV-006 - MEDIUM - FHIRPath string/STU helper arity validation remains incomplete

Carried from review-25. Add exact signatures for `trim`, `split`, `join`,
`matchesFull`, `escape`, `unescape`, `encode`, and `decode`.

### REV-007 - HIGH - Qualified ValueSet references from included CQL libraries lower to missing CTEs

Carried from review-25. Resolve `Lib.ValueSetName` through included terminology
symbols or raise a clear translation error instead of synthesizing
`SELECT * FROM "Lib.ValueSetName"`.

### REV-008 - HIGH - Generic CQL ValueSet membership embeds QICore-specific behavior

Carried from review-25. Move `qicore-notDoneValueSet` behavior out of generic
Python/native terminology membership and behind a profile/IG adapter or
registry-driven configuration.

### REV-030-002 - HIGH - Decimal `HighBoundary` / `LowBoundary` mishandle negative values and coarser precision

Carried from review-30. Decimal boundary helpers still need sign-aware
arithmetic/quantization for negative values and requested precision lower than
the authored scale, with parity coverage across translated SQL, Python
fallback, native-loaded, and no-Python extension surfaces.

## Closed Since Review-35

- `REV-035-001` is closed by CQL-17 EXPLORER: malformed non-null public
  `expand` / `expand_points` `per` Quantity JSON now returns SQL NULL across
  Python fallback, native-loaded, and no-Python C++ paths, while omitted or SQL
  NULL `per` still defaults.
- `REV-030-001` remains closed by CQL-12 EXPLORER: generated FHIRPath string
  predicates, including `ext(element, url)`, now use
  `escape_fhirpath_string_literal()` before constructing predicate strings.
- Review-25 `REV-009` remains closed by CQL-06 SKEPTIC: conversion macro
  private-function registration no longer swallows arbitrary unexpected
  exceptions.

## Validation Context

This read-only review did not rerun a separate validation command. The
immediately preceding CQL-20 EXPLORER gate reported full conformance:
ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall
2822/2822.
