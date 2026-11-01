# QA Handoff - SOF-VD-08 HISTORIAN

Scope: SQL-on-FHIR ViewDefinition `select.unionAll`, historical/spec-compliance pass over parser validation, SQL generation, DuckDB execution, and local official fixtures/examples.

Spec anchors checked directly:
- SQL-on-FHIR ViewDefinition logical model: `ViewDefinition.select.unionAll` is `0..*` and references the recursive `select` content.
- SQL-on-FHIR Functional Model: `select` cross-joins rowsets, `unionAll` concatenates branch rowsets while preserving all rows, and branch iterators establish their own `%rowIndex` scope.

Fresh probes run from `.temp/qa/sof_vd_08_historian_fresh_probe.py` against the workspace source, normal C++ registration, and forced Python fallback:
- functional-model root `where` plus branch `where` around telecom/contact branch generation
- duplicate row preservation
- branch `where` scoped to enclosing parent `forEach`
- unionAll inheriting enclosing `%rowIndex`
- nested unionAll recursion with sibling select columns
- repeat branches under unionAll
- missing-column, type-mismatch, and collection-mismatch rejection

Finding:
- QA-001 MEDIUM OPEN: deprecated/importable `fhir4ds.viewdef.union.generate_union_all()` does not honor branch `forEach`. It emits no lateral/unnest join and evaluates branch columns against the root, returning `[(None,), ('p1',)]` for a two-name Patient where SQL-on-FHIR rowset semantics require `[('A',), ('B',), ('p1',)]`. Main `SQLGenerator` ViewDefinition generation passed the corresponding boundary; the defect is in the legacy direct helper.

Notes:
- An initial sandbox failure on nested union recursion was traced to the probe script importing an older installed package when run as a file from `.temp/qa`; the script now inserts the repo root into `sys.path`, and the workspace implementation passes that boundary.
