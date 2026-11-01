# Architect Handoff - CQL-12 SKEPTIC

## Structural Health

Passed. The remediation is localized to the CQL string semantic boundary:
translator-side validation handles statically known invalid CQL before SQL
generation, while direct DuckDB macros guard the public helper surface against
DuckDB coercions. No resource/profile/measure-specific logic was introduced,
and unknown runtime values still proceed to row-resilient execution.

## Audit Notes

The initial fix correctly blocked numeric operands, but the audit found one
guard-order weakness before finalization: typed SQL nulls could bypass direct
macro validation if `IS NULL` was checked before `typeof(...)`. That was fixed
before terminal state by validating `typeof(...)` first while still accepting
untyped NULL and String-typed NULL. Regression coverage now includes those
typed-null direct helper cases.

## QA Quality

QA was sufficient. It targeted the requested SKEPTIC surfaces: null/empty
propagation, 0-based indexes, Unicode characters, malformed/overlong/ReDoS
regex patterns, translated CQL, direct helpers, native-loaded registration,
forced Python fallback, and no-Python runtime. No `RETRY_QA` is needed.

## Issue Status

- `QA-001`: VERIFIED.

## Validation

- Fresh probe passed: `.temp/qa/cql12_skeptic_probe.py`.
- Focused string parity: 5/5.
- Official CQL string operator subset: 162/162.
- Adjacent macro/WASM tests: 70/70.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.
