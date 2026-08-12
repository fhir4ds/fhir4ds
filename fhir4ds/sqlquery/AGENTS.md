# SQLQuery Agent Notes

## Architecture

- One-way dependency: `fhir4ds/sqlquery/` may import from
  `fhir4ds/viewdef/`, but `fhir4ds/viewdef/` MUST NOT import from
  `fhir4ds/sqlquery/`. Verified by
  `grep -rE "import\s+(fhir4ds\.)?sqlquery" fhir4ds/viewdef/` returning
  nothing. (Invariant I-1 from FEATURE_SQL_ON_FHIR_V2_SPEC_COMPLIANCE.md.)
- The runner's materialization step calls
  `viewdef.SQLGenerator().generate(vd)` to translate a ViewDefinition
  into the body of a DuckDB `CREATE OR REPLACE VIEW "<label>" AS <sql>`
  statement. The view name is the `relatedArtifact.label` (validated
  against sql-name, quoted via `viewdef.utils.quote_identifier`).
- Parameter binding uses DuckDB prepared statements with FHIR-type →
  DuckDB-type coercion via `viewdef.types.fhir_type_to_duckdb`. The
  coercion registry is the dict `_FHIR_TYPE_TO_DUCKDB` in
  `viewdef/types.py`. No string interpolation anywhere on the
  parameter path (Invariant I-3).

## Known Fragile Areas

- §M-1 SQLQuery MVP (2026-08-11): Initial implementation of the
  spec's Analytics Layer (Library SQLQuery / SQLView profiles). The
  runner dispatches on `meta.profile` (parser-side) to choose between
  SQLQuery (`https://sql-on-fhir.org/ig/StructureDefinition/SQLQuery`)
  and SQLView (`https://sql-on-fhir.org/ig/StructureDefinition/SQLView`).
  Profile dispatch in the runner's `_materialize_one` is structural
  for dict inputs: ViewDefinitions are detected by `select` + `resource`
  keys (since ViewDefinition has no FHIR `resourceType` field the way
  Library does). Libraries are detected by `resourceType == "Library"`.
  Cycle detection uses a `set` of canonicals currently being resolved;
  any revisit raises `SQLQueryCycleError`. Re-execution against the
  same connection is idempotent via `CREATE OR REPLACE VIEW`. Callers
  sharing a connection across many SQLQuery runs accumulate views; use
  `DROP VIEW "<label>"` to clean up. Supported dialects:
  `application/sql;dialect=duckdb` (preferred) and `application/sql`.
  Other dialects raise `UnsupportedDialectError` at execution time.
  SQLView profile forbids `parameter 0..0`; the parser rejects SQLView
  JSON carrying parameters before the runner sees them. Parameter
  values are validated light-touch in `runner._coerce` (typed
  `SQLQueryTypeError` for clearly incompatible types like str→integer);
  DuckDB's prepared-statement binding handles the actual coercion.
  28 unit + integration tests in `tests/test_smoke.py` and
  `tests/test_integration.py`. Post-implementation:
  viewdef+fhirpath+sqlquery 2710/2710.

## NOT A BUG Registry

- (None yet for this package.)

## Extension Disclosure

The `joins` extension on ViewDefinition is documented separately at
`fhir4ds/viewdef/AGENTS.md` and `fhir4ds-private/docs/joins-extension.md`.
SQLQuery is the spec's intended mechanism for cross-resource work
where joins appear as raw SQL `JOIN` keywords inside `content[].data`.
