# QA Handoff — SOF-SQ-02 (HISTORIAN, iteration 1)

Chunk: SQL-on-FHIR Analytics Layer — Runner materialization, parameter binding, DuckDB execution semantics. All probes against real in-memory DuckDB connections (register_fhirpath, Python-UDF fallback path for the generated ViewDefinition SQL).

## Spec truth re-derived (from /mnt/d/sql-on-fhir-v2 branch `upstream/sqlquery-view-sources`)

- `StructureDefinition-SQLQuery-notes.md` § Query Composition: materialization-vs-inlining, cycle handling, and dependency-depth limits are explicitly **implementation decisions, not mandated**. This adjudicates several probe results as NOT-spec-violations.
- § Parameter Types: "callers must honour" the declared `Library.parameter.type`; value[x] must match declared type (string/integer/date/dateTime/boolean/decimal table).

## Probed (HISTORIAN angles beyond the SKEPTIC's set)

- Mixed dependency graphs: SQLQuery → SQLView → ViewDefinition at depth 2, plus two parallel SQLView deps both resolving distinct VDs — JOIN across both materialized views returns correct rows; declaration-order materialization confirmed. PASS.
- Undeclared `$nope` placeholder in SQL body → DuckDB InvalidInputException (clear message). Acceptable; no spec-mandated typed error. NOT A BUG.
- Dialect content (`application/sql;dialect=duckdb`) + named `$param` binding: binding survives content selection. PASS.
- Dependency resolving to a SQLQuery Library (not SQLView) as a dependency: parser/runner path materializes its content as the view body and executes. PASS (no crash, sensible rows).
- View-name collisions: label overwriting a pre-existing USER VIEW is silent (CREATE OR REPLACE semantics, documented in runner docstring); label colliding with a pre-existing TABLE → DuckDB CatalogException "Existing object pt is of type Table". Materialization strategy is implementation-defined per spec → NOT A BUG (registry entry added).
- 120 named parameters through prepared statements: works. PASS.
- Mid-chain failure (third dep's SQL invalid): raw DuckDB ParserException; first two views remain on the connection. Spec: implementation-defined; runner docstring documents DROP VIEW cleanup for accumulation but not failure-state. Acceptable — registry entry + doc note, no fix mandated.
- Injection regression: string param `'p1' OR '1'='1'` inert. PASS.
- Full coercion matrix regression of the SKEPTIC's 5 fixes: all hold (not-a-date typed error, partial dates → earliest instant, bool-for-integer/decimal rejected, int32/int64 ranges, Decimal accepted, boolean kind enforcement, time literal valid/invalid).

## Found

- QA-001 (MEDIUM): non-string temporal parameter values bypass declared-type coercion. `runner._coerce` returns any non-str `datetime` value verbatim: `datetime.time` accepted for declared `date` (bound as TIME), `datetime.date` accepted for declared `time`, `datetime.datetime` accepted for declared `date` (TIMESTAMP). Declared registry type never reaches DuckDB on this path — the same defect class the SKEPTIC fixed for string values. Expected: `SQLQueryTypeError` with declared-vs-got.
- QA-002 (LOW): `_bind_parameters` comment asserts prepared SQL "would only consume the names it references" — empirically false (DuckDB rejects declared-but-unreferenced params with InvalidInputException). Behavior acceptable; comment must be corrected.

## NOT A BUG Registry additions

- Undeclared SQL-body placeholder → raw DuckDB InvalidInputException (clear; no typed-error mandate).
- Label-vs-user-view silent overwrite and label-vs-TABLE CatalogException: materialization strategy implementation-defined per spec § Query Composition.
- Mid-chain materialization failure leaves earlier dependency views in place; no transactional cleanup mandated.
