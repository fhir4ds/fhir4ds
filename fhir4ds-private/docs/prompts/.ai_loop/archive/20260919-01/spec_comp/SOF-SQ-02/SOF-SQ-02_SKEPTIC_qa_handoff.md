# QA Handoff — SOF-SQ-02 (SKEPTIC, iteration 1)

Chunk: SQL-on-FHIR Analytics Layer — Runner materialization, parameter binding, DuckDB execution semantics.

## Probed (all against real DuckDB connections; `register_fhirpath` connection + plain connection)

- Parameter binding security: dict named-params passed to `con.execute(sql, params)`; no string interpolation on the parameter path; injection payload in string param inert; malicious relatedArtifact label rejected by `sql-name` validation before any DDL; `quote_identifier` used for CREATE VIEW. PASS.
- Cycle detection: self-cycle, mutual 2-cycle (both SQLViews), 3-cycle (F→G→H→F), and root-cycle (top-level A whose chain returns to A's canonical) all raise `SQLQueryCycleError` before DuckDB execution. Diamond deps do not false-positive. PASS.
- Content selection: prefers `application/sql;dialect=duckdb` over `application/sql`; `dialect=postgres` rejected with `UnsupportedDialectError`. PASS.
- Materialization: ViewDefinition dependency → generated SQL → `CREATE OR REPLACE VIEW "my_patients"`; SQLView dep recurses (materializes inner deps first); idempotent re-execution OK; `DROP VIEW` releases the name. PASS.
- Missing required parameter → `SQLQueryTypeError` with name + declared type. Complex types (Quantity/Period/CodeableConcept) → `SQLQueryTypeError` via registry ValueError. integer64 beyond int32 (5e9) works. PASS.

## Found

- QA-001 (HIGH): Declared date/dateTime/time parameters are never coerced to DATE/TIMESTAMP/TIME. `_coerce` computes `duckdb_type` only to gate numeric/boolean isinstance checks; temporal values bind verbatim as VARCHAR. `'not-a-date'` for a declared date silently returns rows (lexicographic VARCHAR comparison); an int for a date surfaces as a raw DuckDB BinderException, not `SQLQueryTypeError`.
- QA-002 (MEDIUM): Python `bool` accepted for declared integer/integer64/decimal (bool is an int subclass).
- QA-003 (MEDIUM): Out-of-int32-range int accepted for declared `integer` (FHIR integer is signed 32-bit).
- QA-004 (MEDIUM): `decimal.Decimal` rejected for declared `decimal` — the faithful FHIR decimal representation per project doctrine.

Spec truth verified against /mnt/d/sql-on-fhir-v2 branch `upstream/sqlquery-view-sources` `input/pagecontent/StructureDefinition-SQLQuery-notes.md` ("Parameter Types": callers must honour the declared type; valueDate/valueDateTime/valueInteger/valueDecimal mapping).
