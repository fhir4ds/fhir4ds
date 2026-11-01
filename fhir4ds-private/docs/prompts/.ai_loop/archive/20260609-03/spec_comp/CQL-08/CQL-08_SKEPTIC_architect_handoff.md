# Architect Handoff - CQL-08 SKEPTIC

Architectural audit found no additional structural issues after the `Coalesce` remediation. The fix keeps overload handling inside the CQL function translator, uses SQL AST nodes rather than raw SQL strings, and adds no resource/profile/measure-specific knowledge. Direct public helper validation remains in the CQL DuckDB UDF boundary, which is the appropriate layer for SQL callers.

QA quality was sufficient for this personality pass: it challenged query-list overloads, direct helper signatures, list/null boundaries, and Boolean predicate truthiness across native-loaded and forced Python fallback registrations. No `RETRY_QA` veto is needed.

Resolved issues:
- `QA-001` HIGH: query-produced `List<T>` arguments to `Coalesce` now return the first non-null value.
- `QA-002` MEDIUM: direct public `Coalesce` now rejects invalid scalar arities.

Recommended fix order: none. All open issues in this CQL-08/SKEPTIC pass are resolved and verified.
