# Architect Handoff: CQL-20 EXPLORER

Structural audit result: PASS. The aggregate remediation follows the CQL
translator boundary instead of adding fixture-specific SQL patches. Query-form
row aggregation now explicitly disambiguates DuckDB system aggregates from
public CQL list macros, and static type validation was generalized to simple
query-produced lists and aliases before SQL generation. This preserves the
translator invariant that CQL type semantics are decided before DuckDB
execution, while leaving dynamic FHIR-derived values on runtime-checked paths.

Golden standard written to `.temp/architect/golden_standard.md`. QA quality was
sufficient: it exercised query-produced lists, direct helper surfaces,
translation errors, null/empty aggregate behavior, mode ties, Product and
GeometricMean edge cases, and Python/native/no-Python parity. No retry veto.

Issues by category: 2 HIGH `SPEC_VIOLATION`, both `VERIFIED`. Recommended fix
order is complete: first avoid macro/row aggregate collision for `Product`,
then infer static query element types for aggregate validation.

Validation reviewed:

- Fresh EXPLORER probe passed.
- Aggregate parity 9/9.
- Adjacent macro/WASM aggregate checks 14/14.
- Official aggregate functions 50/50 and aggregate clause 9/9.
- Full conformance 2822/2822.
