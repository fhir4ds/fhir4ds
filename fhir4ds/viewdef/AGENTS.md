# ViewDefinition Agent Notes

## Known Fragile Areas
- §G-5 spec suite refresh (2026-08-11): Pulled current
  `FHIR/sql-on-fhir.js` tests/ snapshot (134 → 144 tests; 12 new
  `repeat.json` tests covering recursive-traversal + forEach + unionAll
  + constants + nested iteration). Four triage fixes landed:
  (1) `_split_top_level_union_all` and `_has_top_level_where` in
  `test_spec_compliance.py` are depth- and string-aware so generated SQL
  containing UNION ALL *inside* LATERAL subqueries (the SOF-VD-05 ARCH-003
  null-preservation pattern, used by `repeat` inside `forEachOrNull`) is
  not fragmented by the resourceType-filter adapter. Any future generator
  change that introduces top-level UNION ALL should re-verify both helpers.
  (2) `generator.generate_column_expr` wraps uncast `fhirpath_text(...)`
  calls in `NULLIF(..., '')` so an empty FHIRPath collection surfaces as
  NULL, not empty string (FHIRPath empty-collection semantics for
  non-collection columns; see fn_join spec tests). TRY_CAST paths already
  convert empty to NULL via the cast, so the wrap is only needed when no
  SQL cast applies. (3) `_allowed_actual_type_names` extends the `dateTime`
  compat set to `{DateTime, Date, String, dateTime, date, string}` and
  symmetrically extends `date` to accept `DateTime`, because FHIRPath
  boundary functions (`lowBoundary`/`highBoundary`) on date inputs
  legitimately return Date (a strict subtype of DateTime). See fn_boundary
  date lowBoundary/highBoundary spec tests. (4) `datetime.py:_time_boundary`
  preserves input-precision `second`/`ms` (match_list[2]/[3]) and only
  falls back to fill values for components below the input's precision;
  highBoundary of `12:34:00` now correctly yields `12:34:00.999` rather
  than `12:34:59.999`. Post-refresh: ViewDefinition spec 144/144,
  viewdef+fhirpath 2656/2656.
- SOF-VD-05 HISTORIAN iter 3 fixed (2026-07-05): `forEachOrNull`
  with a nested `forEach` was dropping the parent row when the outer
  collection was empty. Per SQL-on-FHIR v2 Process(S, N) algorithm step 3
  (https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.html),
  when `foci` is empty and `forEachOrNull` is defined, the implementation
  MUST emit one row binding ALL columns from `ValidateColumns(V, [])` (including
  columns produced by nested `forEach` / nested `select`) to null. The
  generator already emitted `LEFT JOIN LATERAL` for the outer `forEachOrNull`
  to preserve the parent NULL row, but the inner `forEach` still emitted
  `CROSS JOIN LATERAL` which evaluated `fhirpath(NULL_alias, 'childPath')`
  -> empty collection -> CROSS JOIN with empty -> 0 rows -> the parent's
  preserved NULL row was eliminated. Fix in `fhir4ds/viewdef/generator.py`
  (`_process_selects` forEach branch threads `null_preserve_var`) and
  `fhir4ds/viewdef/unnest.py` (`generate_foreach_unnest` gains a
  `null_preserve_var` parameter). When set, the unnest subquery short-circuits
  the unnest when the enclosing forEachOrNull alias IS NULL (gating the
  VALUES row on `null_preserve_var IS NOT NULL`) and UNION ALLs a single
  synthetic NULL row produced only when the enclosing alias IS NULL. This
  preserves the parent NULL row ONLY when the enclosing forEachOrNull's foci
  is itself empty (Process(S, N) step 3), while keeping ordinary INNER JOIN
  semantics for non-empty wrapper foci (a contact with empty telecom is
  still dropped per Process(S, N) step 2). `_generate_single_resource` also
  tracks forEachOrNull unnest aliases across UNION ALL alternatives and
  suppresses the null row in non-first alternatives that share the same
  wrapper forEachOrNull path, so the spec's "emit one null row total" rule
  holds across union branches. Pre-existing test
  `test_nested_foreach_under_foreachornull_keeps_inner_semantics` was
  updated to reflect the spec-mandated `(patient-2, None)` row that the
  previous buggy behavior silently dropped. Three new regression tests in
  `TestForeachOrNullNestedForeachSpecSofVd05Historian` (B3a outer-empty,
  B3a outer-non-empty control, mixed partial-contact scenario). Post-fix:
  ViewDefinition pytest 1058/1058. Probe at
  `/mnt/d/fhir4ds/fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/iter3/probe_b3_simplified.py`.
  Keep coverage aligned when touching `generate_foreach_unnest` or
  `_generate_single_resource` UNION ALL handling.
- SOF-VD-05 HISTORIAN ARCH-003 follow-up (iter 3, 2026-07-05): the same
  parent-row-drop bug shape that QA-005 fixed for nested `forEach` also
  existed for nested `repeat` under an enclosing `forEachOrNull`.
  `generate_repeat_unnest` (`fhir4ds/viewdef/unnest.py`) emitted an
  unconditional CROSS JOIN LATERAL against `fhirpath_repeat`, which
  eliminated the parent's preserved NULL row when the outer
  forEachOrNull's foci was empty (Process(S, N) step 3 violation). Fix
  mirrors QA-005 exactly: `generate_repeat_unnest` gained a
  `null_preserve_var` parameter; when set, the source VALUES row is
  gated on `{null_preserve_var} IS NOT NULL` and a synthetic NULL row
  is UNION ALLed only when `{null_preserve_var} IS NULL`.
  `_process_selects` repeat branch (`fhir4ds/viewdef/generator.py`)
  threads `null_preserve_var` into the call. `_collect_foreachornull_paths`
  did NOT need extension because it tracks forEachOrNull *wrappers*
  (the dedup unit), not inner unnests; `repeat` is a consumer of the
  null-preserving var just like nested `forEach`. Three regression
  tests in `TestForeachOrNullNestedRepeatSpecSofVd05Architect`. Post-fix:
  ViewDefinition pytest 1061/1061. Probe at
  `/mnt/d/fhir4ds/fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/iter3/probe_arch003.py`.
- SOF-VD-04 SKEPTIC fresh rerun verified clean (2026-07-03): 38-assertion /
  10-battery hypothesis-driven probe targeted collection default false +
  bool-only invariant, multi-value non-collection error, type URI handling
  for primitive/non-primitive, type mismatch reporting, tag 0..* with
  required name/value, and `__post_init__` patterns. All 8 SKEPTIC
  hypotheses empirically rejected. Notable confirmations: `Column.__post_init__`
  (added by SOF-VD-03 SKEPTIC 2026-07-03) enforces all spec invariants at
  construction; `forEachOrNull` null-row correctly projects SQL NULL for
  child collection columns (preserves SOF-VD-05 HISTORIAN invariant); tags
  with whitespace-only name/value correctly rejected; non-collection multi-
  value path raises typed runtime error at execution. Two informational
  observations (not bugs): `_URI_RE = r"^\S*$"` matches empty string at the
  regex layer but `validate_optional_uri_string` guards before the regex;
  `ColumnType.normalize_name` strips the resource-type prefix for
  `URL#fragment` form (matches FHIR canonical URL semantics). Probe at
  `/mnt/d/fhir4ds/.temp/qa/sof_vd04_skeptic_2026_07_03_fresh/probe.py`.
  Post-iteration: ViewDefinition pytest 1055/1055, full conformance
  2822/2822 (ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47).
- SOF-VD-03 EXPLORER fresh rerun fixed (2026-07-03):
  `validate_required_string` at `fhir4ds/viewdef/types.py:47` only checked
  `not value`, which is True only for empty strings. It did not reject
  whitespace-only strings, so `column.path`, `select.forEach`,
  `select.forEachOrNull`, `where.path`, `column.tag.name`, and
  `column.tag.value` silently accepted whitespace-only values at
  construction/parse time. The malformed value propagated through
  `Column.__post_init__`, parser, `Select.to_dict`, and only surfaced at
  SQL generation with a misleading message ("FHIRPath expression must be a
  non-empty string" — even though the string was non-empty). Per spec,
  `column.path` / `forEach` / `forEachOrNull` / `where.path` are FHIRPath
  expressions, and FHIRPath §3 lexical grammar requires at least one
  expression token; whitespace-only strings are not valid FHIRPath
  expressions. Fix: tightened `validate_required_string` to also reject
  whitespace-only strings via `value.strip()`. This is the central choke
  point used by all the affected fields, so adding the check here fixes
  the entire class of pathological input at the model boundary instead of
  patching each caller individually. Regression class
  `TestWhitespaceFhirPathRejectionPerSpecSofVd03Explorer` in
  `test_parser.py` (22 tests). Post-fix: ViewDefinition pytest 1055/1055
  (was 1033), full conformance 2822/2822 unchanged. Probe at
  `/mnt/d/fhir4ds/.temp/qa/sof_vd03_explorer_2026_07_03_fresh/probe.py`.
- SOF-VD-03 HISTORIAN fresh rerun fixed (2026-07-03):
  `parse_view_definition()` and `ViewDefinition.to_dict()` did not reject
  duplicate column names in the effective output schema, even though the
  SQL-on-FHIR v2 `ValidateColumns` algorithm step 2.1 throws "Column Already
  Defined" and the parser already enforced duplicate `Constant.name` at parse
  time. The duplicate was previously caught only by
  `SQLGenerator._validate_unique_output_names()` (strict, at generate) and
  `validate_view_definition()` (permissive warnings). Fix: added an
  effective-output-schema duplicate-name check in `parse_view_definition()`
  (parser.py, after the select-parsing loop) and in `ViewDefinition.to_dict()`
  (types.py, after each `select.to_dict()` validates container shapes). The
  helper counts each select's direct columns, nested select effective schemas,
  and only the first `unionAll` branch's effective schema (matching
  `SQLGenerator._collect_select_output_schema`), so legitimate matching
  unionAll branch schemas are not flagged. Regression class
  `TestDuplicateColumnNameRejectionPerSpecSofVd03Historian` in
  `test_parser.py` (9 tests). Two existing generator tests updated to assert
  the parser path now rejects. Post-fix: ViewDefinition pytest 1033/1033
  (was 1024), full conformance 2822/2822 unchanged. Probe at
  `/mnt/d/fhir4ds/.temp/qa/sof_vd03_historian_2026_07_03_fresh/probe.py`.
- SOF-VD-03 SKEPTIC fresh rerun fixed (2026-07-03): The `Column` dataclass
  at `fhir4ds/viewdef/types.py:528` had a `__post_init__` that only validated
  `type` and `tag`, deferring `path`/`name`/`description`/`collection`
  validation to `to_dict()` and `SQLGenerator._validate_column_shape`. This
  was the same anti-pattern SOF-VD-02 SKEPTIC fixed for `Constant` on
  2026-07-03 — when a module has multiple spec-owning dataclasses, the
  newest or least-tested one will be missing the `__post_init__` invariant
  its siblings enforce. Direct construction silently accepted
  `Column(path='id', name='')`, `Column(path='', name='x')`,
  `Column(path='id', name='x', description=123)`,
  `Column(path='id', name='_bad')`, `Column(path='id', name='bad-name')`.
  Fix: `Column.__post_init__` at `fhir4ds/viewdef/types.py:546-575` now
  invokes `validate_column_fields(self.path, self.name, self.description)`
  and `validate_optional_boolean(self.collection, "Column.collection")` at
  the top of the method, before the existing type/tag conversion logic.
  Five existing tests that encoded the spec-violation deferral as expected
  behavior were updated to assert construction-time rejection. New
  regression class `TestDirectColumnValidationPerSpecSofVd03Skeptic` in
  `test_columns.py` (8 methods / 13 assertions). Post-fix: ViewDefinition
  pytest 1024/1024 (was 1005), full conformance 2822/2822 unchanged.
  Probe at `/mnt/d/fhir4ds/.temp/qa/sof_vd03_skeptic_2026_07_03_fresh/probe.py`.
- SOF-VD-03 DEFERRED (2026-07-03): `ViewDefinition(select=[])` and
  `Select(...)` lack `__post_init__`, so direct construction with
  spec-invalid shapes (empty root select, non-array columns, etc.) defers
  to `to_dict()`/`generate()`. Per Minimal Footprint and the SOF-VD-02
  SKEPTIC precedent (only Constant was fixed; ViewDefinition/Select
  symmetry was left for a future iteration), this lower-priority symmetry
  concern is DEFERRED. The parser already enforces non-empty select via
  `_parse_select`, and direct dataclass construction with `select=[]` is
  rare. Future SOF-VD chunks adding spec-owning dataclasses should adopt
  the `__post_init__` pattern from the start.
- SOF-VD-02 EXPLORER iter 1 fresh rerun fixed (2026-07-03): The constant
  resolver at `fhir4ds/viewdef/constants.py:resolve_constants_in_path` had a
  silent precedence bug — it checked `if const_name in constants:` BEFORE
  consulting `FHIRPATH_BUILTIN_VARIABLES`. When a user authored a `Constant`
  whose `name` matched a FHIRPath built-in environment variable (`context`,
  `resource`, `rootResource`, `rowIndex`, `ucum`) and referenced `%<name>`
  in a FHIRPath expression, the user's value silently overrode the FHIR
  runtime variable. Per FHIRPath v3.0.0-ballot §"Environment variables",
  builtins are "set for all contexts" and MUST NOT be shadowable by user
  constants. Fix: reordered the resolver to consult `FHIRPATH_BUILTIN_VARIABLES`
  FIRST, preserving `%<name>` verbatim for runtime evaluation. The
  generator's `_validate_constants` (generator.py:1052) was already correct
  (treats builtins as always-defined) — only the resolver had drifted.
  Coverage: `TestBuiltinVariablePrecedencePerSpecSofVd02Explorer` class
  in `test_constants.py` (8 parametrized cases). Post-fix: ViewDefinition
  pytest 1005/1005 (was 997), full conformance 2822/2822 unchanged.
  Probe at `/mnt/d/fhir4ds/.temp/qa/sof_vd02_explorer_2026_07_03_fresh/probe.py`.
- SOF-VD-02 HISTORIAN iter 1 fresh rerun verified clean (2026-07-03):
  7-battery / 141-assertion systematic spec-walkthrough probe confirmed
  all 10 golden-standard invariants for `ViewDefinition.constant` are
  preserved end-to-end (parser → from_dict → Constant → to_dict →
  SQLGenerator → DuckDB execution). All earlier SOF-VD-02
  SKEPTIC/HISTORIAN/EXPLORER fixes remain intact, including the
  2026-07-03 SKEPTIC fix that added `Constant.__post_init__` to enforce
  sql-name + value[x] allowlist uniformly. The supported primitive
  choice list (`CONSTANT_VALUE_TYPE_FIELDS`) matches the official spec's
  19 primitives exactly (no extra historical Coding/CodeableConcept).
  Built-in FHIRPath variables are canonically centralized in
  `constants.py:FHIRPATH_BUILTIN_VARIABLES` and shared by resolver + SQL
  generator. Substitution is FHIRPath-lexical (string literals and
  backtick identifiers not substituted), string values are properly
  escaped as FHIRPath single-quoted literals, and undefined user
  constants raise `ConstantResolutionError`. DuckDB execution parity
  native ↔ forced Python fallback confirmed with spec-expected results.
  Probe at
  `/mnt/d/fhir4ds/.temp/qa/sof_vd02_historian_2026_07_03_fresh2/probe.py`.
  Post-iteration: ViewDefinition pytest 997/997, full conformance
  2822/2822 (ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47).
- SOF-VD-02 SKEPTIC fresh rerun fixed (2026-07-03): The `Constant`
  dataclass at `fhir4ds/viewdef/types.py:687` was missing `__post_init__`,
  unlike sibling spec-owning dataclasses `Column`, `ColumnTag`, and
  `Join`. Direct construction accepted invalid `name` (sql-name
  violations) and unsupported `value_type` values (markdown, Coding,
  CodeableConcept, Address, etc.). The AGENTS.md SOF-VD-02 SKEPTIC
  fresh rerun (2026-05-31) invariant already required direct Constant
  validation, but the dataclass boundary was missed. Fix added
  `Constant.__post_init__` calling the canonical
  `validate_constant_fields(self.name, self.value, self.value_type)`
  helper, matching the pattern of sibling dataclasses. All four
  spec-owning viewdef dataclasses now consistently enforce invariants
  at construction. Regression coverage: `TestDirectDataclassValidation`
  class in `test_constants.py` (8 new test cases). Post-fix:
  ViewDefinition pytest 997/997 (was 985); full conformance 2822/2822
  unchanged. Probe at
  `/mnt/d/fhir4ds/.temp/qa/sof_vd02_skeptic_2026_07_03_fresh/probe.py`.
  Optional future cleanup: Coding/CodeableConcept/null/empty-string
  branches in `resolve_constant` (`fhir4ds/viewdef/constants.py`) are
  now unreachable through normal Constant construction; remain as
  defensive code paths tested via attribute mutation.
- SOF-VD-01 EXPLORER fresh rerun verified clean (2026-07-03):
  42/42 pathological-input probes passed across 6 batteries: resource field
  (missing/empty/array/null/numeric/object/unknown/lowercase/whitespace/
  control-char/100K-char DoS/CJK/newline-injection + valid baseline), profile
  canonical (null/non-array/empty-string/non-string/whitespace/newline/
  very-long/Unicode/Shareable-with-version-suffix/duplicate URLs),
  fhirVersion (null/string/unknown/whitespace/empty/numeric/valid mixed
  R4+R5), shared-table resourceType filtering with DuckDB execution
  (Patient filter, Observation where, zero-matching-resource zero rows,
  forEachOrNull null-row preservation, SQL-injection payload rejected at
  generator guard), pathological VD shapes (10K columns, 100-deep nested
  select, 1K profile entries), and permissive validator (warns for unknown
  resource, accepts absent profile). Probe at
  `/mnt/d/fhir4ds/.temp/qa/sof_vd01_explorer_2026_07_03_fresh/probe.py`.
  Behavioral spec confirmation (NOT A BUG): FHIR `uri` datatype regex is
  officially `\S*` ("very permissive") per https://build.fhir.org/datatypes.html
  — profile canonical values containing Unicode characters such as
  `http://éxample.com/Y` match the spec's `uri` production and are
  spec-compliant when accepted. SQL injection via `resource` is impossible
  because `validate_resource_type()` rejects any non-ResourceType string
  before SQL emission. Conformance 2822/2822 unchanged.
- SOF-VD-01 HISTORIAN fresh rerun fixed (2026-07-03):
  `ViewDefinition.from_dict()` had an over-broad `except Exception` wrapper
  that re-raised every parser exception as a generic `ValueError`, erasing
  the typed `ParseError`/`ValidationError` exception info the parser throws.
  This violated GLOBAL_RULES.md "No Silent Fallbacks: Fail fast with typed
  exceptions." Fix made `SQLOnFHIRError` inherit from `ValueError` so all
  typed errors remain catchable as ValueError for backward compatibility,
  and removed the over-broad wrapper in `from_dict` so typed exceptions
  propagate directly. Regression test:
  `test_from_dict_preserves_typed_parse_error_per_spec_sof_vd01_historian`.
  Probe at `/mnt/d/fhir4ds/.temp/qa/sof_vd01_historian_2026_07_03_fresh/probe.py`.
  ViewDefinition pytest 985/985; conformance 2822/2822.
- SOF-VD-01 SKEPTIC fresh rerun verified clean (2026-07-03):
  38/38 hypothesis-driven probes passed across parser (resource 1..1
  ResourceType binding, profile 0..* canonical, fhirVersion 0..* FHIRVersion
  binding), public `ViewDefinition.from_dict`, direct dataclass
  `SQLGenerator.generate`, DuckDB execution over mixed-resource shared table,
  permissive `validate_view_definition`, and the official `view_resource.json`
  fixture. The shared-table resourceType filter, direct-dataclass generator
  guards, and permissive validator warnings remain aligned with prior
  SKEPTIC/HISTORIAN/EXPLORER fixes. Probe at
  `/mnt/d/fhir4ds/.temp/qa/sof_vd01_skeptic_2026_07_03_fresh/probe.py`.
  Non-blocking architectural observation: `_generate_multi_resource_union`
  (generator.py:1779-1797) is unreachable dead code because
  `validate_resource_type` rejects non-string resources before SQL generation;
  preserved for historical compatibility, low-priority cleanup candidate.
- Release 0.0.8 Domain 5 SPECIALIST verified clean (2026-06-07):
  Fresh composed ViewDefinition probing found no new issues across
  `forEachOrNull` row preservation, nested `unionAll`, branch-local `where`,
  constants, shared `source_table` resource filtering, native-loaded versus
  forced Python fallback execution, and invalid `unionAll` parser/generator
  boundaries. Keep `.temp/qa/domain5_specialist_probe.py`, full
  ViewDefinition pytest, and `conformance/scripts/run_viewdef.py` aligned when
  changing iterator, union, constant, or type/schema validation paths.
- SOF-VD-12 EXPLORER fresh rerun verified clean (2026-06-01):
  combined ShareableViewDefinition and TabularViewDefinition `meta.profile`
  declarations with version suffixes still activate supported profile
  constraints correctly, official JSON field names round-trip, XML input fails
  with the explicit unsupported-format error, and unsupported top-level
  `mapping` remains ignored and omitted. Metadata-heavy valid views execute
  identically under native-loaded DuckDB FHIRPath and forced Python fallback.
  Scratch probes under `.ai_loop/.temp` must prepend the repository root, not
  `fhir4ds-private`, or they can import an installed package and report stale
  ViewDefinition behavior.
- SOF-VD-12 HISTORIAN fresh rerun fixed (2026-06-01): supported
  ShareableViewDefinition and TabularViewDefinition profile activation must
  include inherited CanonicalResource metadata constraints. The official
  profile pages mark `ViewDefinition.status` as `1..1` with required
  PublicationStatus binding, so parser, direct serializer/generator, and
  permissive validator paths now reject or warn when a supported profiled
  ViewDefinition omits `status`. Keep
  `.ai_loop/.temp/qa/sof_vd12_historian_probe.py` and focused parser tests
  aligned with profile metadata handling.
- SOF-VD-12 SKEPTIC fresh rerun fixed (2026-06-01): supported
  ShareableViewDefinition and TabularViewDefinition profile constraints must
  be enforced consistently across parser, direct serializer, direct generator,
  and permissive validator boundaries. `ViewDefinition.to_dict()` must not
  emit official JSON for a direct dataclass whose `meta.profile` activates
  Shareable required metadata/column-type rules or Tabular scalar primitive
  column rules, and `validate_view_definition()` must warn for those same
  direct-dataclass violations without raising. Keep
  `test_to_dict_validates_supported_profile_constraints` and
  `test_validate_warns_for_sof_vd12_supported_profile_constraints` aligned
  when touching profile metadata handling.
- SOF-VD-11 EXPLORER fresh rerun fixed (2026-06-01): iterator
  fast paths must still enforce ViewDefinition column type declarations.
  `forEach`/`forEachOrNull`/`repeat` contexts intentionally avoid the normal
  `type().name` guard because unrolled JSON fragments can report
  backend-dependent type names, but they still need portable physical JSON
  shape guards. Direct `$this` numeric/Boolean projections must not build
  mixed-type `COALESCE(..., VARCHAR)` SQL, and invalid declarations such as
  integer iterator values declared as `string` or `%rowIndex` declared as
  `string`/`boolean` must error instead of silently coercing. Keep
  `sof_vd11_explorer_probe.py`, the iterator primitive regression in
  `test_duckdb.py`, native/fallback parity, ViewDefinition conformance, and
  full conformance aligned when touching `SQLGenerator.generate_column_expr()`
  or iterator type guards.
- SOF-VD-11 HISTORIAN fresh rerun fixed (2026-06-01): direct `%rowIndex`
  columns are a ViewDefinition runner type boundary, not a raw DuckDB ordinal
  leak. SQL-on-FHIR defines `%rowIndex` as integer, and a column declared with
  `type: "integer"` must emit an `INTEGER` result under both native C++
  FHIRPath registration and forced Python fallback. Keep focused `typeof(...)`
  coverage with the official `row_index.json` examples because the generator
  has a fast path that bypasses ordinary FHIRPath UDF casting.
- SOF-VD-11 SKEPTIC fresh rerun fixed (2026-06-01): SQL-on-FHIR View Runner
  official example/spec parity depends on native C++ FHIRPath preserving JSON
  primitive metadata exactly like the forced Python fallback. `fn_boundary`
  runner cases require JSON decimal scale (`1.0` -> precision 1), FHIR
  `date`/`dateTime`/`time` boundary coercion, and typed column guards to agree
  under both backends. `where.json` also depends on root-level
  `where(criteria)` dispatch, not only chained `.where(criteria)`. Keep the
  fresh SOF-VD-11 probe, `test_environment_type_parity.py`, ViewDefinition
  runner regressions, local official spec_tests, and full conformance aligned;
  rebuild/copy the bundled native extension before validating runner parity.
- SOF-VD-10 EXPLORER fresh rerun fixed (2026-06-01): permissive
  `validate_view_definition()` must warn for the same direct-dataclass
  SQL-on-FHIR constraint violations that strict parser/generator paths reject,
  without raising. Keep warnings aligned for ResourceType binding,
  FHIRVersion binding, root `ViewDefinition.name`, `Column.name`, and
  `Constant.name` `sql-name` violations. Strict parse/generation still fail
  fast; direct dataclass `None` remains the omitted metadata representation.
- SOF-VD-10 HISTORIAN fresh rerun verified clean (2026-06-01): Official
  sql-name, sql-expressions, cardinality, ResourceType/FHIRVersion binding,
  and local `expectError` fixture handling remained aligned across parser,
  `ViewDefinition.from_dict()`, `to_dict()`, direct generator guards, and
  DuckDB execution. Preserve the strict/permissive split: parse/generation
  reject invalid official JSON and mutated direct dataclasses, while
  `validate_view_definition()` returns warnings for direct-dataclass issues.
  Keep native-loaded and forced Python fallback execution probes paired when
  these constraint boundaries are touched.
- SOF-VD-10 SKEPTIC fresh rerun fixed (2026-06-01): strict
  `parse_view_definition()` / `ViewDefinition.from_dict()` must distinguish an
  absent optional root metadata field from a present JSON null. Root
  `resourceType`, `id`, `meta`, `url`, `version`, `status`, `title`, and
  `description` are omitted when absent, but present null is invalid FHIR JSON
  shape and must raise before dataclass construction. The parser now routes
  those fields through `_parse_optional_root_metadata()` before shared metadata
  validation; direct dataclass `None` still means omitted metadata.
- SOF-VD-09 SKEPTIC fresh rerun fixed (2026-06-01): root
  `ViewDefinition.where` is an official logical-model serialization boundary,
  not just a parser/generator preflight concern. `ViewDefinition.to_dict()`
  must route root `where` through the same `validate_where_conditions()` helper
  as parser, `ViewDefinition.from_dict()`, `Select.to_dict()`, and
  `SQLGenerator.generate()` so missing `path` or null/non-string
  `description` cannot be emitted as official JSON.
- SOF-VD-08 SKEPTIC fresh rerun fixed (2026-06-01): strict official JSON
  parsing must reject a present empty `select.unionAll: []` instead of
  normalizing it to absence. `unionAll` is a rowset-producing branch list; when
  it appears, it must contain at least one selection structure, and FHIR JSON
  empty repeating properties should be omitted. Keep parser and
  `ViewDefinition.from_dict()` coverage aligned while preserving direct
  dataclass `Select.unionAll=[]` as the default absent state.
- Release 0.0.7 Domain 5 verified clean (2026-05-24): Fresh
  ViewDefinition domain testing found no new issues across `forEachOrNull`,
  nested select/unionAll, root/select `where`, constants, type columns, and
  column collision guards. `ViewDefinition.from_dict()` currently delegates to
  `parse_view_definition()`, and legacy join helpers validate and quote
  aliases/resource table names. Keep full unit/integration/spec-compliance
  coverage, conformance `run_viewdef.py`, and native-vs-forced-fallback
  execution probes together when changing these paths.
- SOF-VD-12 EXPLORER verified clean (2026-05-20): Boundary probes for
  combined Shareable+Tabular `meta.profile` declarations with version suffixes,
  unsupported profile URL aliases, top-level unsupported `mapping` input,
  official JSON field-name round trips, explicit XML-unsupported behavior, and
  metadata-heavy DuckDB execution all passed against current source. Unsupported
  `mapping` is ignored and omitted from `to_dict()`; keep this documented
  behavior consistent unless the logical model adds a supported mapping field.
- SOF-VD-12 HISTORIAN verified clean (2026-05-20): Fresh parser,
  serializer, SQL generation, and DuckDB execution probes confirmed
  Shareable/Tabular `meta.profile` constraints, CanonicalResource metadata
  retention, official JSON field-name round trips, explicit XML-unsupported
  behavior, and ignored unsupported top-level `mapping` input. Keep official
  example execution paired across native C++ FHIRPath registration and forced
  Python fallback when revisiting profile/metadata behavior.
- SOF-VD-12 SKEPTIC fixed (2026-05-20): ViewDefinition
  `meta.profile` must activate supported logical-model profile constraints.
  ShareableViewDefinition requires root `url`, `name`, `fhirVersion`, and
  every `select.column.type`; TabularViewDefinition forbids collection columns
  and non-primitive column types. Root CanonicalResource metadata such as
  `url`, `version`, and `status` is retained by the parser/serializer without
  changing generated SQL execution. XML parsing is intentionally
  unsupported unless a dedicated XML parser is added; document that boundary
  explicitly instead of surfacing only a generic invalid-JSON parse error.
- SOF-VD-11 EXPLORER verified (2026-05-20): ViewDefinition runner probes for
  Patient key projection, Observation filtering, Patient.address `forEach`,
  `forEachOrNull`, `%rowIndex` filters, collection typed output, and parser
  rejection paths pass against the current source tree under both native C++
  DuckDB registration and forced Python fallback. Scratch scripts under
  `.ai_loop/.temp` must prepend the repo root to `sys.path`; otherwise they can
  accidentally import an installed package and report stale ViewDefinition
  behavior.
- SOF-VD-11 HISTORIAN fixed (2026-05-20): SQL-on-FHIR View Runner helper
  functions `getResourceKey()` and `getReferenceKey()` must work under both
  native C++ DuckDB registration and forced Python fallback. The Python
  fallback already returned canonical `ResourceType/id` keys, but native C++
  treated these functions as unknown and generated NULL rows in official
  PatientDemographics/PatientAddresses/UsCoreBloodPressures-style
  ViewDefinitions. Keep runner example tests paired across native/fallback and
  rebuild/copy `fhirpath.duckdb_extension` after touching native FHIRPath.
- SOF-VD-11 SKEPTIC fixed (2026-05-20): Observation ViewDefinition
  execution with a decimal `valueQuantity.value` column must work on both
  native C++ registration and forced Python fallback. The generator's runtime
  type guard asks FHIRPath for `(valueQuantity.value).type().name`; fallback
  FHIRPath must report numeric Quantity values as `decimal`, not the broad
  `.value` suffix fallback `string`, or valid filtered Observation views raise
  a collection/type guard error only on fallback.
- SOF-VD-10 EXPLORER fixed (2026-05-20): strict
  `parse_view_definition()` must reject present JSON null for repeating
  logical-model fields such as `constant`, `profile`, and `fhirVersion`.
  Absence remains valid for optional fields, but a present field must preserve
  FHIR JSON shape rules: repeating elements are arrays and properties are not
  null. Keep `ViewDefinition.from_dict()` aligned through its parser
  delegation, and keep permissive `validate_view_definition()` limited to
  direct dataclass warning inspection.
- SOF-VD-10 HISTORIAN fixed (2026-05-20): keep parser and generator strict for
  SQL-on-FHIR `sql-expressions`, but keep
  `parser.validate_view_definition()` permissive. It should collect warnings
  for direct-dataclass issues such as combined `forEach`/`forEachOrNull`/
  `repeat`, missing `column.path`, and missing `column.name`; it must not raise
  before returning its warning list. Strict parse and SQL generation paths have
  separate guards for the same error constraints.
- SOF-VD-10 SKEPTIC fixed (2026-05-20): parser/public
  `ViewDefinition.from_dict()` enforce the SQL-on-FHIR `sql-name` invariant on
  optional `ViewDefinition.name`, and strict SQL generation validates direct
  dataclass root `name`, `fhirVersion`, and `Constant.name`/`value[x]`
  bypasses before SQL generation. Keep parser coverage for required
  `resource`, `select`, `column.path`, `column.name`, `constant.name`,
  `constant.value[x]`, `where.path`, ResourceType binding, FHIRVersion binding,
  and forEach/forEachOrNull/repeat mutual exclusion aligned with direct
  generator guard paths while preserving `validate_view_definition()` as a
  permissive warning API.
- SOF-VD-09 SKEPTIC fixed (2026-05-20): root/select
  `where` predicates must not coerce non-Boolean FHIRPath results into
  inclusion. ViewDefinition SQL uses exact `fhirpath_json(...) = '[true]'`
  predicates instead of the permissive public `fhirpath_bool` convenience UDF,
  so numeric/string results such as `valueInteger`, `1`, or `"true"` do not
  satisfy root/select where constraints. Keep native C++ and forced Python
  fallback parity for this generated SQL boundary.
- SOF-VD-09 SKEPTIC fixed (2026-05-20): `where.description` is optional
  string/markdown metadata and should be validated at parser,
  `ViewDefinition.from_dict()`, and generator direct-dataclass boundaries while
  preserving valid strings. Do not preserve present numeric/null description
  values as opaque dict extras.
- SOF-VD-08 EXPLORER fixed (2026-05-20): the deprecated/importable
  `UnionGenerator.validate_union_columns()` helper is still a public
  compatibility surface and must validate the same effective union branch
  schema as `generate_union_all()` and `SQLGenerator`: column name, order,
  declared FHIR type, and `collection` cardinality. Name-only warnings can
  falsely bless spec-invalid `unionAll` branches even though execution rejects
  them later; the helper now compares effective schema triples.
- SOF-VD-08 HISTORIAN fixed (2026-05-20): the legacy/importable
  `fhir4ds.viewdef.union.generate_union_all()` helper must preserve the same
  rowset semantics as main `SQLGenerator` for branch `forEach`,
  `forEachOrNull`, `repeat`, nested `select`, branch `where`, and nested
  `unionAll`. Do not implement direct union helpers by only rendering branch
  columns against the root resource; that silently drops iterator rows and
  nested branch columns even though the main ViewDefinition generator is
  correct.
- SOF-VD-08 SKEPTIC fixed (2026-05-20): `select.unionAll` rowsets compose
  like ordinary `select` rowsets. Multiple sibling unionAll groups, and nested
  unionAll groups under a parent select, must be expanded into branch
  combinations and cross-joined with sibling selects rather than concatenated
  as independent SQL UNION groups. Effective output-schema validation must also
  include each unionAll rowset's first-branch schema so sibling union groups
  cannot silently project the same column name.
- SOF-VD-08 SKEPTIC fixed (2026-05-20): A unionAll branch may contain direct
  columns plus nested select/unionAll columns. Branch schema collection and SQL
  generation must preserve both the branch-local columns and nested union
  columns in column order; treating a branch's direct columns as a reason to
  ignore nested unionAll output silently drops data.
- SOF-VD-07 EXPLORER fixed (2026-05-20): `select.repeat` over raw deeply
  nested JSON must preserve native C++ and forced Python fallback parity beyond
  Python/orjson recursion limits. The fallback `fhirpath_repeat` path now
  parses with a depth-derived recursion budget under the repeat fallback
  recursion-limit lock, traverses iteratively, and uses iterative JSON
  serialization for repeated child nodes. Keep raw JSON ViewDefinition coverage
  for nested `QuestionnaireResponse.item` depth above the default Python
  recursion ceiling; dict fixtures serialized with `json.dumps` can hide this
  class of bug before DuckDB is reached.
- SOF-VD-07 HISTORIAN fixed (2026-05-20): ViewDefinition
  `select.repeat` columns and repeat entries may explicitly use `$this` as the
  current repeated-node focus. Keep forced Python fallback and native C++
  parity for `$this.linkId`, `$this.text.exists()`, and repeat expressions
  such as `$this.item`; otherwise columns can silently return NULL only on the
  fallback path even though ordinary relative paths like `linkId` work.
- SOF-VD-07 SKEPTIC fixed (2026-05-20): `select.repeat` entries are
  FHIRPath expressions, not only dotted JSON keys. ViewDefinition SQL routes
  repeat traversal through `fhirpath_repeat`, so the Python fallback and native
  C++ UDF must both evaluate each repeat expression at the current repeated
  node, recursively visit object results to any parsed depth, union duplicate
  node hits across paths, and preserve column evaluation against each repeated
  node. Keep parser/generator validation rejecting scalar JSON `repeat:
  "path"`; present `repeat` is a 0..* array field.
- SOF-VD-07 SKEPTIC fresh rerun fixed (2026-06-01): a present empty
  `select.repeat: []` is invalid FHIR JSON shape for the repeat directive and
  must not be treated as repeat absence/default `$this`. Parser,
  serializer, and direct SQL generator validation now share the central repeat
  validator so empty repeat arrays fail before generated SQL can skip
  `fhirpath_repeat`. Keep the fresh probe and parser/generator/repeat coverage
  aligned with ViewDefinition conformance.
- SOF-VD-07 HISTORIAN fresh rerun verified clean (2026-06-01): official
  recursive repeat semantics remain aligned across parser,
  `ViewDefinition.from_dict()`, `Select.to_dict()`, direct
  `SQLGenerator.generate()`, native-loaded DuckDB, and forced Python fallback.
  Keep coverage for multiple repeat FHIRPath expressions, duplicate path
  union/de-duplication, `$this` traversal cycle guards, deep nested
  QuestionnaireResponse-style trees, `%rowIndex`, and repeated-node column
  context together with the empty-repeat rejection guard.
- SOF-VD-07 EXPLORER fresh rerun verified clean (2026-06-01): repeat stayed
  aligned across native-loaded DuckDB and forced Python fallback under edge
  combinations: overlapping repeat paths with repeated-node `where`, nested
  `forEachOrNull` below repeat, `%rowIndex` columns on repeated nodes,
  `$this` self-traversal as a cycle-style guard, malformed direct
  `fhirpath_repeat` path arrays, and deep raw JSON. Preserve `%rowIndex` as
  the stable traversal-position signal; physical SQL row order may still need
  an explicit sort by callers when a select-level filter is present.
- SOF-VD-06 EXPLORER fixed (2026-05-20): `%rowIndex` is a
  ViewDefinition/FHIRPath environment variable, not only a standalone pseudo
  column. Columns and select `where` predicates inside `forEach`/
  `forEachOrNull` must support `%rowIndex` embedded in larger FHIRPath
  expressions such as `iif(%rowIndex = 0, ...)` or `%rowIndex = 1`; otherwise
  the DuckDB FHIRPath UDF sees an undefined variable and silently returns
  NULL/empty rows. The generator now substitutes the active row-index SQL
  value into the FHIRPath expression argument before calling DuckDB UDFs.
- SOF-VD-06 EXPLORER fixed (2026-05-20): Embedded `%resource` and
  `%rootResource` references inside iterator expressions must still target the
  root resource, not the unnested item. Root-only embedded expressions route to
  the root input; expressions that mix root variables with current-focus paths
  or `%context` fail fast because the public DuckDB FHIRPath UDF accepts one
  JSON context input.
- SOF-VD-06 SKEPTIC fresh rerun fixed (2026-06-01): strict parser/public
  constructor input must distinguish absent iterator fields from present JSON
  null. `select.forEach` and `select.forEachOrNull` are optional `0..1 string`
  FHIRPath fields; absent means no iterator, while present null is invalid
  official JSON and must raise before SQL generation. Direct dataclass
  `Select(forEach=None)` / `Select(forEachOrNull=None)` still means omitted.
- SOF-VD-06 HISTORIAN fresh rerun verified clean (2026-06-01): official
  `forEach`/`forEachOrNull` semantics remain aligned across parser,
  serializer/direct dataclass guard paths, SQL generation, native-loaded DuckDB,
  and forced Python fallback. Keep row multiplication, empty `forEach`
  suppression, `forEachOrNull` null-row preservation, nested column focus,
  `%context` current-item routing, `%resource`/`%rootResource` root routing, and
  `%rowIndex` substitution in where/column/child iterator expressions covered
  together.
- SOF-VD-06 EXPLORER fresh rerun verified clean (2026-06-01): iterator
  composition remains aligned across native-loaded DuckDB and forced Python
  fallback when parent `%rowIndex` is embedded in child iterator expressions
  such as `%context.given[%rowIndex]`, sibling nested `forEachOrNull` null rows
  are combined with sibling `forEach` row suppression, and top-level
  `%rowIndex` evaluates to 0. Mixed current/root built-ins in one expression
  should continue to fail fast until the DuckDB FHIRPath UDF surface supports
  multiple JSON contexts.
- SOF-VD-06 HISTORIAN fixed (2026-05-20): The SQL-on-FHIR
  `sql-expressions` constraint applies to all three iterator fields. Parser,
  `ViewDefinition.from_dict()`, direct dataclass validation, and generator
  guard paths must reject any `select` that combines `forEach`,
  `forEachOrNull`, and/or `repeat`; do not defer this to SQL generation only.
- SOF-VD-06 HISTORIAN fixed (2026-05-20): Leading `%context.`,
  `%resource.`, and `%rootResource.` expressions may include ordinary FHIRPath
  functions or predicates, not only dot navigation. Route the whole tail to the
  correct current/root JSON input in ViewDefinition SQL generation. If an
  iterated expression mixes root and current built-ins in one FHIRPath string,
  fail fast rather than evaluating it against the iterator alias and returning
  plausible but wrong rows.
- SOF-VD-06 SKEPTIC fixed (2026-05-20): ViewDefinition iterators change the
  current column evaluation context to the unnested element, but FHIRPath
  `%resource` and `%rootResource` must still resolve to the containing/root
  resource for that element. Do not blindly pass `%resource.*` or
  `%rootResource.*` paths to `fhirpath_*` with the iterator alias as the input;
  generator routing preserves root-resource context while keeping `%context`
  relative to the iterated element and `%rowIndex` relative to the iterator.
- SOF-VD-05 EXPLORER fixed (2026-05-20): `unionAll` branch schema
  validation must compare effective column name, order, declared FHIR type, and
  `collection` cardinality. Matching names alone are insufficient; otherwise a
  spec-invalid union can be accepted and coerced only by the physical SQL
  backend. Direct generator guard paths must also validate recursive
  `select`/`unionAll`/`column` containers as arrays of dataclass objects so
  public dataclass construction cannot bypass parser shape checks or fail with
  raw `TypeError`/`AttributeError`.
- SOF-VD-05 HISTORIAN fixed (2026-05-20): nested `select` is a full
  recursive `contentReference` to `ViewDefinition.select`, so a child
  `select` containing `unionAll` must be processed at any depth even when no
  parent `forEach`/`forEachOrNull`/`repeat` context exists. Do not limit nested
  union hoisting to iterator parents; default `$this` wrapper selects must
  still emit the union branch rows and combine parent columns with branch
  columns.
- SOF-VD-05 EXPLORER fresh rerun fixed (2026-06-01): direct dataclass
  serialization of recursive nested `select.where` must share parser/generator
  validation. `Select.to_dict()` now routes non-empty `where` values through
  `validate_where_conditions()` and rejects `where=None`, so malformed objects
  such as missing `path` or non-string/null `description` cannot be emitted
  under child selects. Keep serializer, parser/public constructor, and
  generator direct-input guards aligned for recursive `select.select`
  contentReference boundaries.
- SOF-VD-04 EXPLORER fixed (2026-05-20): `collection=true` primitive
  typed columns must preserve the declared primitive element type in generated
  DuckDB output. `fhirpath()` returns `VARCHAR[]`, so generator collection
  expressions explicitly cast integer/boolean/numeric primitive declarations
  with DuckDB `list_transform` while preserving string/date/time and complex
  JSON representations.
- SOF-VD-04 HISTORIAN fixed (2026-05-20): `column.type` element ID
  notation such as `Observation.referenceRange` must not be fed directly into
  simple `type().name` equality guards. FHIRPath engines may report a
  datatype-like runtime name such as `Range`/`range` for that backbone element;
  SQL generation should preserve element-ID declarations while still enforcing
  cardinality.
- SOF-VD-04 HISTORIAN fixed (2026-05-20): `$this` column expressions bypass
  the normal simple-path runtime type guard path. Keep explicit SQL JSON-shape
  safeguards for non-primitive `$this` values when `column.type` is unset or
  primitive, especially inside `forEach` contexts where `$this` can be a
  complex element.
- SOF-VD-04 SKEPTIC fixed (2026-05-20): `column.collection` defaults to
  false, and public SQL generation/execution must report an error when a
  non-collection column produces multiple values. Do not rely on permissive
  `fhirpath_text()` first-value behavior for scalar ViewDefinition columns.
- SOF-VD-04 SKEPTIC fixed (2026-05-20): `column.type` is a FHIR
  StructureDefinition URI field, not only the local enum spelling. Preserve
  relative/full FHIR URIs, require explicit type for non-primitive outputs, and
  report primitive/non-primitive mismatches instead of silently returning text
  or NULL.
- SOF-VD-04 SKEPTIC fixed (2026-05-20): `column.tag` is a 0..* backbone
  element with required string `name` and `value`. Parser, public
  `ViewDefinition.from_dict()`, and direct dataclass/generator guard paths must
  validate and preserve tags; database/type-hint tags are metadata unless an
  implementation explicitly handles them.
- SOF-VD-04 SKEPTIC fresh rerun fixed (2026-05-31): column metadata uses the
  singular official `tag` field only. Do not accept or canonicalize a plural
  column-level `tags` alias at strict parser/public-constructor boundaries, and
  revalidate `ColumnTag.name` / `ColumnTag.value` in serializer and direct
  SQL-generator guard paths so mutated dataclass objects cannot emit invalid
  official JSON or execute with malformed metadata.
- SOF-VD-04 HISTORIAN fresh rerun fixed (2026-05-31): non-simple FHIRPath
  column expressions such as `code.coding.where(...)` must still report
  non-primitive JSON object/array results when `column.type` is unset or
  primitive-incompatible. Keep the narrow expression guard in SQL generation:
  simple navigation paths use full `type().name` checks, while non-simple
  expressions only reject physically complex JSON results whose runtime type
  names are absent or incompatible, preserving official primitive boundary
  functions such as `lowBoundary()` / `highBoundary()`.
- SOF-VD-04 EXPLORER fresh rerun fixed (2026-06-01): non-simple primitive
  FHIRPath expressions with a declared `column.type` must not silently coerce
  incompatible primitive values to NULL. When `type().name` reports a runtime
  type for a non-simple expression, generated SQL now checks it against the
  declared primitive type so cases like `'abc'` as `integer` or `1` as
  `string` raise column type errors in native-loaded and forced Python
  fallback execution. Keep temporal boundary functions in the compatibility
  set: the conformance runner's `VARCHAR` resource transport can report
  `String` for valid `dateTime`/`time` `lowBoundary()` and `highBoundary()`
  outputs, while JSON transport reports the temporal System type directly.
- Milestone code review finding (2026-05-20, OPEN): Public
  `ViewDefinition.from_dict()` must stay in lockstep with
  `parse_view_definition()` for root metadata and `where` parsing. It currently
  accepts invalid `resource`/`profile`/`fhirVersion` shapes and can silently
  drop parser-supported root `where` dict/string filters during SQL generation.
  Remediation should reuse shared parser/type helpers or delegate dict
  construction through the parser, with regression tests at both boundaries.
- Milestone code review finding (2026-05-20, OPEN): Legacy public join helpers
  in `join.py` interpolate join aliases/resources into generated SQL. Validate
  `join.name` as SQL-on-FHIR `sql-name`, validate `join.resource` against
  ResourceType metadata, and quote aliases/table references before treating
  joins as executable SQL generation surface.
- SOF-VD-03 EXPLORER fixed (2026-05-20): Select iteration fields need
  logical-model shape validation before SQL generation. `forEach` and
  `forEachOrNull` are optional string FHIRPath expressions, while `repeat` is a
  repeating string field; do not coerce arbitrary iterables such as dicts into
  repeat path lists.
- SOF-VD-03 EXPLORER fixed (2026-05-20): `column.collection` is a boolean
  logical-model field. String values such as `"false"` must not be accepted or
  interpreted through Python truthiness, because that changes scalar columns
  into collection-valued SQL output.
- SOF-VD-03 HISTORIAN fixed (2026-05-20): Treat present `null` values for
  repeating select containers (`column`, nested `select`, `unionAll`) as invalid
  parser/public-constructor input, not as absent arrays. SQL-on-FHIR inherits
  FHIR JSON repeating-element shape: present repeating elements are arrays.
- SOF-VD-03 HISTORIAN fixed (2026-05-20): Duplicate output column-name checks
  must include the effective schema produced by `unionAll` plus sibling/parent
  columns. Matching names across branches are required, but a branch column must
  not collide with sibling columns projected into the same output row.
- SOF-VD-03 SKEPTIC fixed (2026-05-20): Select/column parser validation
  must enforce logical-model container and primitive shapes at the parser and
  public `ViewDefinition.from_dict()` boundaries. `ViewDefinition.select` is a
  non-empty array, `select.column`/nested `select`/`unionAll` are arrays of
  objects, `column.path` and `column.name` are non-empty strings, `column.name`
  must satisfy SQL-on-FHIR `sql-name` without a leading underscore, and
  `column.description` must be markdown/string metadata when present. Generic
  SQL table identifier quoting remains separate from ViewDefinition output
  column sql-name validation.
- SOF-VD-03 SKEPTIC fresh rerun fixed (2026-05-31): Parser and
  `ViewDefinition.from_dict()` can be strict while direct dataclass
  `SQLGenerator.generate()` and official `to_dict()` serialization bypass
  select/column rules. Keep direct root `select` non-empty validation aligned
  with parser cardinality, and keep `Column.to_dict()` / `Select.to_dict()` /
  `ViewDefinition.to_dict()` from emitting invalid official JSON for empty root
  select, missing/invalid `column.path`, invalid `column.name`, non-markdown
  `column.description`, or non-Boolean `column.collection`.
- SOF-VD-03 EXPLORER fresh rerun fixed (2026-05-31): Parser/public-constructor
  input must reject a present JSON null `select.column.description`. Direct
  dataclass `Column(description=None)` still means absent metadata, but parsed
  official JSON must distinguish missing from present-null because
  `column.description` is a `0..1 markdown` primitive.
- SOF-VD-02 EXPLORER fixed (2026-05-20): Constant substitution must be
  FHIRPath-lexical, not regex-only. `%name` inside FHIRPath string literals is
  literal text, while `%name` outside literals is an external constant; string
  constant values must be escaped as FHIRPath string literals before the
  generated FHIRPath expression is SQL-escaped.
- SOF-VD-02 EXPLORER fixed (2026-05-20): `valueInteger64` is a FHIR primitive
  represented as a JSON string in FHIR JSON. ViewDefinition parsing must reject
  JSON-number `valueInteger64` even if the numeric range is otherwise valid.
- SOF-VD-02 HISTORIAN fixed (2026-05-20): Constant validation must stay
  primitive-only for `ViewDefinition.constant.value[x]`. The current SQL-on-FHIR
  choice list does not include historical complex `valueCoding` or
  `valueCodeableConcept`, and FHIR primitive values need type/range/lexical
  validation before parser or public constructor acceptance.
- SOF-VD-02 HISTORIAN fixed (2026-05-20): Public convenience constructors must
  parse the spec singular `constant` field consistently with
  `parse_view_definition`; otherwise constants disappear before `%name`
  validation/substitution reaches SQL generation.
- SOF-VD-02 SKEPTIC fixed (2026-05-20): `ViewDefinition.constant.name`
  must enforce the SQL-on-FHIR `sql-name` invariant
  `^[A-Za-z][A-Za-z0-9_]*$`; accepting names such as `_bad`, `bad-name`, or
  `bad.name` lets parser state and FHIRPath `%name` reference extraction drift.
- SOF-VD-02 SKEPTIC fixed (2026-05-20): `ViewDefinition.constant.value[x]`
  must be exactly one supported primitive choice. Do not silently choose the
  first of multiple `value*` fields, accept unknown `valueFoo`, or rely on
  fallback casing for supported choices such as canonical and integer64.
- SOF-VD-01 SKEPTIC fixed (2026-05-20): `ViewDefinition.resource` must remain a single required FHIR `ResourceType` code. Parser and generator now reject arrays and unknown resource codes; do not reintroduce array/multi-resource root support unless the SQL-on-FHIR logical model changes.
- SOF-VD-01 SKEPTIC fixed (2026-05-20): `ViewDefinition.profile` and `ViewDefinition.fhirVersion` are logical-model declarations and must be parsed/preserved with validation even though they do not currently alter generated SQL.
- SOF-VD-01 SKEPTIC fresh rerun (2026-05-31): `ViewDefinition.profile`
  is a 0..* `canonical(StructureDefinition)` declaration, not an arbitrary
  string list. Parser and direct generator guard paths must reject present
  non-arrays, null arrays, non-string members, empty strings, and canonical
  strings with whitespace while preserving valid version-suffixed canonical
  URLs. The shared `validate_canonical_array()` helper is the guard for root
  `profile`, `meta.profile`, serialization, and direct SQL generation.
- SOF-VD-01 HISTORIAN fresh rerun (2026-05-31): `ViewDefinition.to_dict()`
  is an official JSON serialization boundary, not a best-effort dump of direct
  dataclass attributes. It must reuse the same root logical-model validators as
  parser and SQL generation for `resource`, `profile`, `fhirVersion`, and
  CanonicalResource metadata such as `meta.profile`; otherwise direct
  dataclass construction can emit invalid ViewDefinition JSON even though
  parser/generator reject it.
- SOF-VD-02 SKEPTIC fresh rerun (2026-05-31): `ViewDefinition.constant` is the
  singular official JSON field. Reject the legacy plural `constants` alias in
  strict parser/public-constructor paths, reject duplicate constant names before
  `%name` substitution, and keep direct `Constant` objects validated by the same
  primitive `value[x]` allowlist/range/shape rules as parser dictionaries.
  `resolve_constants_in_path()` must raise `ConstantResolutionError` for
  undefined user constants while preserving built-in FHIRPath variables such as
  `%resource`.
- SOF-VD-02 HISTORIAN fresh rerun (2026-05-31): Verified clean after the fresh
  SKEPTIC fixes. Parser, public constructor, serializer, direct dataclass
  generator preflight, lexical resolver substitution, native-loaded DuckDB
  execution, and forced Python fallback all preserve the current SQL-on-FHIR
  constant contract for the singular `constant` array, `sql-name` names,
  exactly-one primitive `value[x]`, undefined user constants, and built-in
  `%resource`/`%rootResource`/`%rowIndex` pass-through. Keep official
  `constant.json` and `constant_types.json` evidence paired with fresh probes.
- SOF-VD-02 EXPLORER fresh rerun (2026-05-31): Constant FHIR primitive
  validation must reject partial `dateTime`/`instant` strings that attach a
  time component to an incomplete date, such as `2024T00:00:00Z` or
  `2024-01T00:00:00Z`. `dateTime` values with a time component require a
  complete `YYYY-MM-DD` date and timezone, and `instant` requires full date,
  time, and timezone. Keep parser, `Constant.from_dict()`, `Constant.to_dict()`,
  and direct `SQLGenerator` dataclass validation aligned.

## NOT A BUG Registry

- SOF-VD-05 HISTORIAN iter 3 (2026-07-05): String constants substituted into
  `forEach` paths produce literal-string foci, not navigation. Per FHIRPath
  `%Const` substitutes the constant's *value* into the expression — a string
  constant becomes a FHIRPath string literal `'name'`, not the bare
  navigation path `name`. forEach over a literal string is not navigation;
  this is a fundamental FHIRPath limitation, not a fhir4ds bug. The spec's
  only constant example (`code=%bp_code` in a where predicate) substitutes
  into a comparison, which is the intended use. Direct dataclass / parser /
  generator paths all behave consistently with this FHIRPath semantic.
- SOF-VD-09 EXPLORER fresh rerun (2026-06-01): Root `where`
  stays scoped to the root resource when projections use composed rowset
  features. Fresh native-loaded and forced Python fallback probes verified
  constants, exact singleton Boolean true filtering, false/empty/null/string/
  numeric/multi-item non-inclusion, `where.description` retention, parser /
  `to_dict()` / direct generator malformed-shape rejection, and root context
  preservation through `forEach`, `forEachOrNull`, `repeat`, nested `select`,
  and `unionAll`. Keep `fhirpath_json(...) = '[true]'` exactness and root
  environment routing together when changing generated filter SQL.
- SOF-VD-09 HISTORIAN fresh rerun (2026-06-01): Verified clean against
  official SQL-on-FHIR v2 root `where` semantics. Root `where` predicates keep
  only exact singleton Boolean true results (`fhirpath_json(...) = '[true]'`);
  false, empty, missing/null, strings such as `'true'`, numeric literals, and
  ordinary scalar values are row-exclusion signals rather than inclusion
  signals. Constants and complex FHIRPath predicates resolve before SQL
  generation, valid `where.description` metadata is retained, malformed
  `where.path`/`where.description` is rejected at parser/serializer/direct
  generator boundaries, and root filters stay scoped to the root resource even
  when projections use `forEach`, `unionAll`, or branch-local `where`.
- SOF-VD-08 HISTORIAN fresh rerun (2026-06-01): Verified clean against
  official SQL-on-FHIR v2 `unionAll` semantics. `unionAll` concatenates branch
  rowsets without de-duplicating, branch schemas must match by count/name/order/
  declared FHIR type/collection flag, and nested `unionAll` composes like an
  ordinary `select` rowset. Branch-local `where` filters stay branch scoped,
  root/select filters wrap their own scope, and direct dataclass
  `Select.unionAll=[]` remains the absent/default state even though present
  official JSON `unionAll: []` is rejected.
- SOF-VD-08 EXPLORER fresh rerun (2026-06-01): Verified clean with pathological
  `unionAll` compositions across parser, serializer, direct dataclass,
  SQL-generation, native-loaded DuckDB FHIRPath, and forced Python fallback.
  Keep coverage for duplicate-preserving branches, scoped root/branch `where`,
  `forEachOrNull` null-valued branch rows, nested `unionAll`, `repeat` branches,
  malformed direct dataclass items, and branch schema mismatches together.
- SOF-VD-07 EXPLORER fresh rerun (2026-06-01): SQL row order after
  repeat-level filtering is not a conformance signal by itself. The repeat
  generator provides `%rowIndex` for traversal position, and probes should
  assert ordering-sensitive behavior through `%rowIndex` rather than relying
  on unsorted physical DuckDB result order.
- SOF-VD-05 SKEPTIC fresh rerun (2026-06-01): Fresh nested-select probes
  verified parser, `to_dict()`, direct `SQLGenerator`, native-loaded DuckDB,
  and forced Python fallback behavior for recursive `select.select`
  contentReference semantics. Child selects inherit parent `forEach`/
  `forEachOrNull` focus, no-iterator children default to `$this`, parent/child
  and sibling rowsets compose by the SQL-on-FHIR recursive Cartesian model, and
  an empty nested select under a column-bearing parent behaves as an identity
  rowset. Preserve duplicate-name checks across parent/child select recursion.
- SOF-VD-05 HISTORIAN fresh rerun (2026-06-01): Verified clean against the
  official nested-select and multiple-select definitions. Recursive
  `select.select` contentReference behavior is preserved through parser,
  serializer, direct dataclass generation, native-loaded DuckDB execution, and
  forced Python fallback. A parent `forEachOrNull` with no match produces a
  null-preserved row, and child columns in that null row are SQL NULL even when
  the child column is collection-valued; do not normalize those null-row
  values to empty arrays.
- SOF-VD-09 EXPLORER verified clean (2026-05-20): Root `where`
  predicates that produce empty/null, non-Boolean strings such as `"true"`,
  or multi-item Boolean collections such as `true | false` are not inclusion
  signals. Generated SQL requires exact singleton Boolean true and preserves
  root-resource scope for `$this`, leading `%resource`, and embedded
  `%resource`/`%rootResource` expressions in both native C++ and forced Python
  fallback execution.
- SOF-VD-09 HISTORIAN verified clean (2026-05-20): A valid FHIRPath
  expression used as root `where` that returns a non-Boolean scalar, such as
  `id`, `'true'`, or `1`, is not a row-inclusion signal. Generated
  ViewDefinition SQL requires exact singleton Boolean true
  (`fhirpath_json(...) = '[true]'`), so these cases are excluded
  row-resiliently in both native C++ and forced Python fallback execution.
- SOF-VD-05 SKEPTIC (2026-05-20): A nested child `forEach` under an
  enclosing `forEachOrNull` keeps its own inner-flattening semantics. If the
  outer `forEachOrNull` creates a NULL row and the child `forEach` has no
  collection to iterate, that child branch may produce no row. This matches the
  SQL-on-FHIR functional model precedence (`forEachOrNull` then `select`) and
  the official `foreach.json` unionAll cases, where null-preserved rows are not
  duplicated by child `forEach` branches.
- SOF-VD-01 SKEPTIC (2026-05-20): With `SQLGenerator(source_table="resources")`, generated SQL must add a `json_extract_string(t.resource, '$.resourceType') = '<resource>'` filter. This preserves one ViewDefinition's single root resource type when several resource types share one physical table.
- SOF-VD-01 HISTORIAN verified clean (2026-05-20): `profile` and `fhirVersion` are logical-model declarations parsed and preserved on `ViewDefinition`; they do not currently change generated SQL. Root resource execution still comes from `resource` plus the physical table/resourceType filter contract.
- SOF-VD-01 EXPLORER verified clean (2026-05-20): A root `Patient` ViewDefinition over a shared mixed-resource table should filter out non-Patient rows while still allowing zero-or-more output rows per Patient. `forEachOrNull` preserving a Patient row with null nested columns is required behavior, not a leak from the resourceType filter.
- SOF-VD-01 EXPLORER fresh rerun (2026-05-31): Parser input,
  direct dataclass construction, `to_dict()`, `SQLGenerator(source_table=...)`,
  and DuckDB execution all preserve the single-root-resource contract after the
  SKEPTIC/HISTORIAN fixes. A shared mixed `resources` table must filter rows by
  the validated `ViewDefinition.resource`, while `forEachOrNull` may still
  produce a null-valued child row for a matching resource with no child
  collection. Root `profile` and `fhirVersion` declarations remain
  validated/preserved metadata and do not change row-producing SQL semantics.
- SOF-VD-02 HISTORIAN fresh rerun (2026-05-31): It is expected that
  SQL-on-FHIR built-in FHIRPath environment variables remain unresolved by the
  user constant resolver. `%resource`, `%rootResource`, `%context`, `%rowIndex`,
  and `%ucum` are runtime variables, while any other undefined `%name` is a
  user constant error.

## Architecture

- SOF-VD-09 SKEPTIC (2026-05-20): Treat `where` as a
  ViewDefinition-specific exact-Boolean SQL boundary. Public convenience UDFs
  such as `fhirpath_bool` may remain permissive for broader SQL callers, but
  generated SQL-on-FHIR filters must require the FHIRPath result to serialize
  as singleton Boolean true and must preserve root/current context routing.
  Keep `where` metadata validation centralized in `types.py` and reused by
  parser, public constructor, and generator guard paths.
- SOF-VD-08 EXPLORER (2026-05-20): Keep `unionAll` effective schema
  extraction centralized. Deprecated/importable helpers such as
  `UnionGenerator.validate_union_columns()` may be legacy, but while public
  they must delegate to the same `(name, type, collection)` schema boundary as
  `generate_union_all()` and main `SQLGenerator`.
- SOF-VD-08 SKEPTIC (2026-05-20): Treat `unionAll` as a rowset-producing
  select expression, not as a top-level SQL string mode. SQL generation expands
  union branches into alternatives, then composes those alternatives with
  sibling selects via the same rowset cross-join semantics as ordinary nested
  selects. Effective schema collection is the shared source for duplicate
  output-name validation and branch compatibility.
- SOF-VD-05 EXPLORER (2026-05-20): Treat `unionAll` output schema as
  name/order/FHIR-type/collection-cardinality, not just a sequence of SQL
  aliases. Parser validation and direct generator dataclass guardrails must
  enforce the same recursive container boundaries for `column`, `select`, and
  `unionAll` before SQL generation starts.
- SOF-VD-05 HISTORIAN (2026-05-20): Treat nested `select` and `unionAll`
  as the same recursive `ViewDefinition.select` grammar at every depth.
  Parent context inheritance includes explicit iterators and the implicit
  default `$this` context; hoisting/generation logic must not special-case
  only iterator parents.
- SOF-VD-05 SKEPTIC (2026-05-20): Preserve the official row-composition
  layering for nested selects. `forEachOrNull` is a row-preserving iterator for
  its own expression, while descendant `select`, child `forEach`, and
  `unionAll` composition still follow their normal row-set semantics; do not
  broaden child iteration behavior based only on an enclosing null-preserved
  context.
- SOF-VD-03 EXPLORER (2026-05-20): Keep select iteration field and
  `column.collection` validation centralized in `types.py` helpers and reused
  by parser, public `ViewDefinition.from_dict()`, and generator direct-input
  guard paths. Parser/public constructors should fail typed logical-model shape
  errors before SQL generation; generator guards are the final safety net for
  manually constructed dataclasses.
- SOF-VD-03 HISTORIAN (2026-05-20): Keep `unionAll` validation split into two
  concerns: branch alternatives must match each other by column name/order, and
  each effective branch schema must remain duplicate-free against sibling and
  parent projected columns. Do not collapse those rules into a global duplicate
  check that rejects legitimate matching branch schemas.
- SOF-VD-03 SKEPTIC (2026-05-20): Keep ViewDefinition output column
  validation centralized through shared type helpers and reused by parser and
  public `ViewDefinition.from_dict()`. Keep generator-side column-name
  validation as the final guard for direct dataclass construction, but do not
  reuse the stricter SQL-on-FHIR `sql-name` rule for implementation-controlled
  table references.
- SOF-VD-04 SKEPTIC (2026-05-20): Keep `collection`, `type`, and `tag`
  validation split by responsibility: parser/types enforce logical-model JSON
  shape and URI/tag metadata, while generator execution guards enforce
  result-cardinality and only safe runtime type checks. Broad `type().name`
  wrapping over all FHIRPath expressions regresses valid literals, functions,
  and nested unrolled element contexts.
- SOF-VD-04 HISTORIAN (2026-05-20): Element-ID `column.type` declarations are
  FHIR element-shape metadata, not runtime `type().name` strings. `$this`
  paths need their own JSON-shape guard because they intentionally bypass
  normal path navigation and may point at a complex current focus.
- SOF-VD-01 EXPLORER (2026-05-20): Keep root metadata validation centralized in `metadata.py`; parser and generator should consume shared ResourceType/FHIRVersion constants instead of drifting into separate allowlists.
- SOF-VD-01 SKEPTIC fresh rerun (2026-05-31): Keep logical-model
  root-field primitive/container validators centralized in `types.py`.
  Parser, serializer, and direct generator guard paths must consume the same
  helpers for `resource`, `profile`, `fhirVersion`, and CanonicalResource
  metadata so direct dataclass construction cannot bypass strict JSON parsing.
- SOF-VD-01 EXPLORER fresh rerun (2026-05-31): Keep the root-resource
  execution contract end-to-end: strict parser/dataclass validation feeds one
  validated `resource` code into the generator, shared-table SQL injects the
  explicit `resourceType` predicate, and FHIRPath column/iterator execution
  stays on the registered DuckDB UDF surface for both native and forced Python
  fallback registrations.
- SOF-VD-02 SKEPTIC (2026-05-20): Keep constant `name` and `value[x]` validation metadata centralized in `types.py` so parser and public convenience constructors enforce the same supported field set and exactly-one behavior.
- SOF-VD-02 SKEPTIC fresh rerun (2026-05-31): Treat direct `Constant`
  dataclass input and `Constant.to_dict()` as official logical-model
  boundaries. They must reuse the same `types.py` value[x] metadata and
  primitive validators as parser dictionaries. Constant resolver construction
  must reject duplicate names, and undefined user constants must raise at the
  resolver boundary; do not rely on downstream FHIRPath evaluation to discover
  those errors.
- SOF-VD-02 HISTORIAN (2026-05-20): Keep FHIR primitive constant value
  validation centralized before substitution. SQL generation should only consume
  parsed `Constant` objects through `ConstantResolver`; it must not rediscover
  `value[x]` fields or rely on DuckDB/FHIRPath coercion to reject invalid
  primitive constants later.
- SOF-VD-02 HISTORIAN fresh rerun (2026-05-31): Treat `types.py` as the
  constant value-choice metadata owner, `parser.py` and `Constant.to_dict()` as
  logical-model boundaries, `constants.py` as the sole lexical substitution
  boundary, and `generator.py` as a consumer of already validated `Constant`
  objects. Do not add parallel constant allowlists or regex-only replacement in
  generator code.
- SOF-VD-02 EXPLORER (2026-05-20): Keep FHIRPath lexical scanning for
  constants centralized in `constants.py`; generator validation and substitution
  must share the same scanner so `%name` handling cannot drift between
  preflight and execution.
