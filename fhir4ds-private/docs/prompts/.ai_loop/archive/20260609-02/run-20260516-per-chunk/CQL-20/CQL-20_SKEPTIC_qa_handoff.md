# QA Handoff - CQL-20 SKEPTIC Aggregate Functions

## Scope

Active run: CQL-20, SKEPTIC, Aggregate Functions.

Spec sources checked:
- CQL Reference v1.5.3 Appendix B, Aggregate Functions.
- CQL Logical Specification v1.5.3 AggregateExpression definitions.
- CQL Reference v1.5.3 Arithmetic Add rule for compatible Quantity unit conversion.

## Hypotheses Tested

1. Direct public SQL macros may accidentally use DuckDB row aggregates even though CQL aggregate functions take list arguments.
2. Native C++ aggregate UDFs and Python fallback UDFs may diverge where the official XML suite does not cover edge cases.
3. Quantity aggregates may reduce Quantity JSON to numeric values and lose unit semantics.
4. Null-only and null-containing aggregate lists may not preserve CQL special cases for Count, AllTrue, AnyTrue, and statistical functions.
5. No-Python/browser-style registration may miss pure SQL macro coverage that native-loaded Python supplements hide.

## Findings

### QA-001 - Direct Boolean List Aggregate Macros Broken

Severity: HIGH.

Evidence from fresh direct DuckDB probes:
- `AllTrue([true, NULL, true])` raised a `bool_and(BOOLEAN[])` binder error.
- `AnyTrue([false, NULL])` raised a `bool_or(BOOLEAN[])` binder error.

Additional compatibility note from remediation:
- Raw direct SQL calls such as `Median([1, 2, 3])` cannot be macro-shadowed under the CQL name without breaking existing DuckDB row aggregate usage such as `Median(x) FROM (...)`.
- The CQL list signatures for Median/Mode/StdDev/Variance and population variants are therefore validated through translated CQL SQL and the `statistical*` list helper surface, not by replacing DuckDB's row aggregate names.

Spec basis: CQL aggregate functions have list signatures and ignore null elements, with special null-source behavior for AllTrue and AnyTrue.

### QA-002 - Python/C++ statisticalMode Tie Divergence

Severity: MEDIUM.

Evidence from fresh direct DuckDB probes:
- Forced Python fallback `statisticalMode([1.0, 1.0, 2.0, 2.0])` returned `1.0`.
- Native/no-Python C++ `statisticalMode([1.0, 1.0, 2.0, 2.0])` returned SQL NULL.

Spec basis: Mode is a public aggregate surface; parity is required even where the official XML suite lacks a tied-mode case.

### QA-003 - Quantity Aggregates Lost Unit Semantics

Severity: HIGH.

Evidence from fresh translated CQL probes:
- `Sum({1 'g', 1000 'mg'})` returned `{"value":1001.0,"unit":"g"}`.
- `Avg({1 'g', 1000 'mg'})` returned `{"value":500.5,"unit":"g"}`.
- `Median({1 'g', 2000 'mg', 3 'g'})` returned `{"value":3.0,"unit":"g"}`.

Spec basis: aggregate overloads include Quantity, and CQL Quantity arithmetic requires compatible unit conversion with the most granular compatible result unit.

## Probe Artifact

Fresh regression probe: `.temp/qa/cql20_skeptic_probe.py`.

Post-remediation probe result: `CQL-20 SKEPTIC aggregate probe passed`.
