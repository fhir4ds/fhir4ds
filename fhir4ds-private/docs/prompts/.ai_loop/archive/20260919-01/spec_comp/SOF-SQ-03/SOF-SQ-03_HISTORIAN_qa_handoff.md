# QA Handoff — SOF-SQ-03 (iteration 1, HISTORIAN)

## Scope
Cross-package integration, error model integration, public API surface of `fhir4ds/sqlquery` (chunk SOF-SQ-03), tested against the tree as left by the SKEPTIC launch's 4 fixes. Probes: `.temp/qa/historian_probe1.py`, `.temp/qa/historian_probe2.py`, plus an inline nested-resolver-failure probe.

## Re-verification of SKEPTIC fixes (all PASS, regression-free)
- Resolver isinstance branch: parsed ViewDefinition AND parsed SQLView objects (incl. a SUBCLASS instance) materialize correctly in the same dependency list as dict forms (probe 1 cases 1, 6: rows (2,1,1,2) / (1,)).
- Typed error wrapping: dependency Catalog/Binder errors, inner parse errors, and param'd-SQLQuery-as-dependency InvalidInput all surface as `SQLQueryMaterializationError` with label+canonical, `__cause__` preserved (probes 3, 3b, 11).
- Ambiguity carve-out intact (code-verified `_resolve_view_sql`).
- parameter.name sql-name validation enforced (`SQLQueryValidationError` via validator; bool-as-int and 32-bit range rejected with typed `SQLQueryTypeError`, probe 12).

## Newly verified (mandate items, no issue)
- Two-level chain recursion, cycle raised before execution (probe 5).
- Round-trip: parse → to_dict → re-parse → to_dict dict-equal, SQL bytes equal, executes identically (probe 2).
- `from fhir4ds.sqlquery import *` lands exactly `__all__`; all 26 names defined and accurate; `DependencyResolver` is a runtime typing alias resolving to `Callable[[str], Union[Dict, ViewDefinition, SQLQuery, SQLView]]`.
- Placeholder rewriting edges: `:minut` vs substring-safe, `::` cast, quoted-literal colons, comments (probe 7).
- Dialect preference duckdb > plain sql; other dialects typed `UnsupportedDialectError` (probes 8–9).
- Native C++ extension path vs Python fallback parity on a VD-backed SQLQuery: identical rows on both (probe 13).
- Nested two-level failure context: inner resolver failure carries the INNER label+canonical (documented carve-out; outer context visible via traceback chain, `__cause__` = KeyError).

## Issues (OPEN)
- **QA-005 (LOW)**: main SQL body execution errors (duckdb Binder/Catalog) escape raw — dependency-materialization errors are typed but the main body's are not. No mandate item requires wrapping; author SQL is outside the threat model. Candidate for INTENDED.
- **QA-006 (LOW)**: `SQLQueryRunner.__init__` resolver docstring understates the resolver contract (omits parsed SQLQuery/SQLView objects accepted per `DependencyResolver`). Docstring-only fix.

sqlquery suite: 109/109 before fixes. Advancing to FIX.
