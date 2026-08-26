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

- (2026-08-24, SOF-SQ-03 HISTORIAN) Main-body execution errors (duckdb
  Binder/Catalog from the author's own `content[].data` SQL) escape
  `SQLQueryRunner.execute()` raw — NOT wrapped in the typed hierarchy.
  Rationale: no spec/chunk mandate covers main-body engine errors; the
  module threat model excludes author-controlled SQL; wrapping would mask
  duckdb diagnostics. Dependency-materialization errors ARE typed
  (`SQLQueryMaterializationError` with label+canonical).
- (2026-08-24, SOF-SQ-03 HISTORIAN) Nested two-level resolver failure
  surfaces the INNER failing level's label+canonical only (outer context
  visible via the exception chain/traceback). Documented carve-out in
  `_materialize_one`; `__cause__` preserved.

## Extension Disclosure

The `joins` extension on ViewDefinition is documented separately at
`fhir4ds/viewdef/AGENTS.md` and `fhir4ds-private/docs/joins-extension.md`.
SQLQuery is the spec's intended mechanism for cross-resource work
where joins appear as raw SQL `JOIN` keywords inside `content[].data`.

### HISTORIAN launch discoveries (2026-08-24)

- Round-trip fidelity now requires per-entry `extra_fields` bags
  (SQLContent/SQLRelatedArtifact/SQLParameter) plus verbatim `meta` /
  `type_concept` on `_SQLLibraryBase`; `to_dict` appends the profile
  canonical only when no recognized declaration is present — never rewrite
  a declared official canonical. Known-but-unmodeled FHIR keys
  (description, publisher, extension, ...) flow through the top-level
  extra_fields bag (`_MODELED_LIBRARY_KEYS` is the exclusion set).
- Parse-time enforcement added: `Library.status` 1..1 (base Resource),
  `parameter.type` must be a FHIR primitive (validated via the
  `fhir_type_to_duckdb` registry — data-driven), `type.coding.system` when
  present must be LibraryTypesCodes. All raise typed `SQLQueryParseError`.
- Fragile spot: fixtures that omit `status` now fail fast; keep
  `status: "active"` in all Library test fixtures.

### EXPLORER launch discoveries (2026-08-24)

- Adversarial volume/edge battery (100-entry content arrays, 50
  relatedArtifacts, 64 parameters, base64 edge forms, malformed JSON
  shapes, 3-generation mutation-stable round-trips, e2e runner): zero
  actionable defects; all rejection paths typed with per-entry index
  context and first-bad-entry precedence.
- INTENDED (do not "fix"): strict base64 rejects URL-safe alphabet,
  embedded whitespace/newlines, and padding variants; `type.coding`
  with the expected code pinned to a foreign system is rejected even
  when a later coding is valid; SQLView tolerates `parameter: []`
  (0..0 counts elements, not the JSON key).
- Spec-legal behaviors confirmed: duplicate parameter names, relatedArtifact
  label colliding with a parameter name, `resource` values like
  `http://vd|1.0.0#x` (kept verbatim), BOM'd unicode SQL round-trips
  byte-exact, 1MB SQL bodies parse.
- Deferred (QA-003): runner `select_best_content` is exact-match on
  `application/sql` / `application/sql;dialect=duckdb`, so
  `application/sql;charset=utf-8` passes the parse-side
  sql-must-be-sql-expressions invariant but raises
  `UnsupportedDialectError` at execution. Parse side is spec-correct;
  charset tolerance would be an optional runner enhancement.
- e2e reminder: runner-generated ViewDefinition SQL needs
  `register_fhirpath(con)` (or `fhir4ds.connect()`) on the caller's
  connection, else DuckDB CatalogException on `fhirpath()`.

## SOF-SQ-02 SKEPTIC launch (2026-08-24) — Runner parameter coercion fidelity
- Fixed 5 (1 HIGH + 4 MEDIUM) in `runner.py::_coerce`: the registry-derived DuckDB type was computed but never applied to temporal params — date/dateTime/time values bound verbatim as VARCHAR, so `'not-a-date'` silently produced lexicographic-compare results and non-strings surfaced as raw DuckDB errors (QA-001, HIGH). Temporal strings now cast through a DuckDB prepared `SELECT CAST(? AS <type>)` (registry-whitelisted type name, value bound — never interpolated) and failures raise `SQLQueryTypeError` with declared-vs-got detail. QA-002: Python `bool` (int subclass) rejected for integer/integer64/decimal. QA-003: int32/int64 range enforced for `integer`/`integer64` (FHIR signed-width). QA-004: `decimal.Decimal` accepted for `decimal` (converted to float). QA-005: FHIR partial dates (`2020`, `2020-06`) and partial dateTimes normalize to the earliest instant of the stated period before the cast (strict regex grammar; garbage still rejected).
- Regression tests: `fhir4ds/sqlquery/tests/test_integration.py::TestParameterCoercionFidelity` (19). Suite 89/89.
- NOT A BUG Registry: cycle detection verified complete for self-cycle, mutual 2-cycle (SQLViews), 3-cycle, and root-cycle back to the executed library's own canonical; diamond dependencies do not false-positive. Parameter path injection-safe end-to-end (dict named-params to `con.execute`; `sql-name` label validation + `quote_identifier` on DDL).

## SOF-SQ-02 EXPLORER runner launch (2026-08-24) — Spec-example placeholders + tz determinism
- Fixed 2 (both HIGH) in `runner.py`:
  - QA-001: official spec-example SQL bodies use `:name` placeholders (sql-on-fhir-v2 `sql-query-examples.fsh` `:city`; `StructureDefinition-SQLQuery-notes.md` SQL Annotations `:patient_id`/`:from_date`); DuckDB only accepts `$name`/`?`, so such bodies died with a raw ParserException. `SQLQueryRunner._rewrite_named_placeholders` now rewrites declared-and-supplied `:name` tokens to `$name` before execution. The scanner skips single-quoted literals (`''` escapes), double-quoted identifiers, `--`/`/* */` comments, and the `::` cast operator; undeclared `:name` tokens are left verbatim so the engine's original error surfaces. Values remain prepared-statement bound — never interpolated.
  - QA-002: tz-aware native datetime params bound host-timezone-dependently (10:30+00:00 → 05:30 on host tz −5) while the same instant as a string cast to wall time 10:30. `_coerce` now normalizes aware datetimes to naive wall time (`replace(tzinfo=None)`) before the registry CAST: deterministic across hosts and identical to the string path.
- Regression tests: `TestSpecExamplePlaceholders` (6) + `TestTimezoneAwareDatetimeBinding` (2); sqlquery suite 102/102; master gate 2832/2832.
- NOT A BUG Registry additions: (1) Positional/mixed `?` bodies surface raw engine errors — named placeholders (`$name`/`:name`) are the only supported form (consistent with prior adjudication of raw undeclared-placeholder errors). (2) duckdb 1.5.2 `CAST('24:00:00' AS TIME)` returns a str — engine quirk, pass-through. (3) Dependency mechanics verified clean: 30-deep SQLView→VD chain (correct, ~0.02 s), idempotent re-execution, clean rebuild after mid-chain `DROP VIEW`, interleaved queries on one connection, None binds as SQL NULL, same param referenced 3× binds once, unicode/emoji values round-trip, DATE/TIMESTAMP params yield typed result columns with microsecond fidelity.

## SOF-SQ-03 HISTORIAN launch (2026-08-24) — Cross-package integration audit
- Re-verified all 4 SKEPTIC fixes regression-free (resolver isinstance branch
  incl. SUBCLASS instances, typed materialization-error wrapping with
  label+canonical + `__cause__`, Library/select ambiguity carve-out,
  parameter.name sql-name validation).
- New verifications (now locked in `TestHistorianLaunch`, 4 tests): mixed
  resolver shapes (dict VD + Library dict + parsed SQLView object) in ONE
  dependency list; parse→to_dict→re-parse byte-stable + identical execution;
  nested resolver failure carries inner label+canonical; duckdb dialect
  preferred over plain `application/sql`; native C++ vs Python-fallback
  parity on VD-backed SQLQuery (identical rows both paths).
- Public API: `from fhir4ds.sqlquery import *` lands exactly `__all__` (26
  names, all accurate). `DependencyResolver` resolves at runtime to
  `Callable[[str], Union[Dict, ViewDefinition, SQLQuery, SQLView]]`.
- Fixed (LOW): `SQLQueryRunner.__init__` resolver docstring understated the
  contract (omitted parsed SQLQuery/SQLView objects); now states the full
  `DependencyResolver` contract. Suite 113/113; gate 2832/2832.

## SOF-SQ-03 EXPLORER final launch (2026-08-24) — Integration-seam boundary sweep
- Zero code defects found; 10 boundary areas verified end-to-end on real
  DuckDB connections (probes: `.temp/qa/explorer_probe1.py`, `explorer_probe2.py`).
- Verified clean: diamond dependency graphs (shared VD canonical
  materialized per consumer edge — rows correct from both consumers;
  idempotent via CREATE OR REPLACE, documented statelessness), depth-5
  mixed chain (SQLQuery→SQLView→SQLQuery→SQLView→VD), main body combining
  a dependency view AND `:param` placeholders, dependency label colliding
  with the SOURCE table name (DuckDB Catalog error typed as
  `SQLQueryMaterializationError`, source table NOT clobbered), unicode/
  emoji SQL-body literals execute byte-correct, unicode labels rejected by
  sql-name (ASCII-only invariant), interleaved runner instances on one
  shared connection, 3-level nested failure surfaces the INNERMOST
  label+canonical with `__cause__` chain, native-vs-fallback parity on the
  depth-5 chain, parameter name equal to a dependency label (no collision).
- NOT A BUG Registry additions: (1) diamond shared canonicals are NOT
  deduplicated (resolver invoked per edge) — spec silent, runner documented
  as stateless, CREATE OR REPLACE keeps it idempotent. (2) Parameters do
  NOT flow through materialized dependency views: a dependency SQLView
  body containing `:param` fails at CREATE VIEW with a typed
  `SQLQueryMaterializationError` (label+canonical) — parameters bind only
  in the main SQLQuery body; SQLView profile forbids parameters, and
  dependency views are static CREATE VIEW statements.
- Suites: sqlquery+viewdef 1354 passed; master gate recorded in launch
  handoffs (final tree).
