# QA Handoff: CQL-18 HISTORIAN

## Scope

- Chunk: CQL-18, List Operators Part 1.
- Personality: HISTORIAN.
- Spec source: CQL Reference Appendix B, List Operators (`https://cql.hl7.org/09-b-cqlreference.html#list-operators-2`).
- Current-source probe: `.temp/qa/cql18_historian_probe.py`.

## Spec Grounding

Appendix B defines list operators over list-valued expressions, not just list literals. The relevant semantics include:

- `contains` / `in`: use equality semantics; null elements are considered equal for membership. Null list input is false for these singleton membership surfaces.
- `distinct`, `except`, and `intersect`: use equality semantics with nulls considered equal for set membership.
- list equality/equivalence is element-wise and order-sensitive.
- `exists` returns true only when the list has any non-null element.
- `flatten`, `First`, and `IndexOf` operate on list expressions with CQL list indexing/equality semantics.

## Findings

### QA-001: Named List Definitions Bypass CQL List Semantics

Severity: HIGH

The fresh probe compared forced Python fallback, native-loaded registration, and no-Python/browser-style C++ for inline list helper calls and named list definitions. Inline helper calls passed on all three surfaces, but named list definitions failed before result comparison because generated population SQL is invalid.

Evidence from generated SQL:

- `LNumeric contains null` and `null in LNumeric` emitted `NULL IN EXISTS (...)`, which DuckDB rejects.
- `LNumeric includes null` and `null included in LNumeric` routed to `intervalContains(...)`.
- `LNumeric except { null }` and `LNumeric intersect { null, 2 }` lowered to SQL `EXCEPT` / `INTERSECT` over a scalar list CTE.
- `distinct LNulls` used DuckDB `list_distinct` instead of `CQLListDistinctEq`.
- List literal definitions were emitted with `resource` columns because `ListExpression` inference defaulted to `UNKNOWN` / `Any`.

All three surfaces raised the same DuckDB `ParserException` on the generated SQL, so this is a translator-layer bug rather than a backend-specific UDF issue.

## Handoff

Proceed to remediation. The likely fix is to infer `ListExpression` as `PATIENT_SCALAR` with `List<T>` type metadata, then route list-typed identifiers through CQL list helper macros for Part 1 operators.
