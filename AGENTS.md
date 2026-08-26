# duckdb-fhirpath - AGENTS.md

**FHIR for Data Science** - A unified suite of high-performance tools for working with FHIR data in analytical environments, built on DuckDB.

## Repository Overview

This repository has been reorganized into a unified `fhir4ds` namespace. All Python source code resides under the `fhir4ds/` directory, organized by feature and backend.

## Package Structure (Unified)

| Feature | Subpackage Path | Purpose |
|---------|-----------------|---------|
| **FHIRPath** | `fhir4ds.fhirpath` | Core FHIRPath parser and evaluator |
| **FHIRPath (DuckDB)** | `fhir4ds.fhirpath.duckdb` | DuckDB integration and C++ extension wrapper |
| **CQL** | `fhir4ds.cql` | CQL to SQL translator for clinical quality measures |
| **CQL (DuckDB)** | `fhir4ds.cql.duckdb` | CQL-specific DuckDB UDFs and macros |
| **ViewDefinition** | `fhir4ds.viewdef` | SQL-on-FHIR v2 ViewDefinition support |
| **DQM** | `fhir4ds.dqm` | Digital Quality Measure orchestrator |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      APPLICATION LAYER                          │
│  CQL Measures  │  FHIRPath Queries  │  ViewDefinitions         │
└────────┬───────────────┬───────────────────┬───────────────────┘
         │               │                   │
         ▼               ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                      TRANSLATION LAYER                          │
│  fhir4ds.cql  │  (direct)          │  fhir4ds.viewdef          │
│  CQL → SQL    │                    │  ViewDef → SQL            │
└────────┬───────────────┴───────────────────┴───────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      UDF LAYER (DuckDB)                         │
│  fhir4ds.fhirpath.duckdb     │  fhir4ds.cql.duckdb             │
│  fhirpath(), fhirpath_text() │  AgeInYears(), DurationInDays() │
└────────┬───────────────────────┴────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      CORE LAYER                                 │
│  fhir4ds.fhirpath                                               │
│  FHIRPath parser and evaluator engine                           │
└─────────────────────────────────────────────────────────────────┘
```

## Subpackage Details

### `fhir4ds.fhirpath`
**Purpose:** Core FHIRPath parser and evaluator.
**Location:** `fhir4ds/fhirpath/`
**Tests:** `fhir4ds/fhirpath/tests/unit/`

### `fhir4ds.fhirpath.duckdb`
**Purpose:** Native DuckDB integration.
**Location:** `fhir4ds/fhirpath/duckdb/`
**Bundled Extension:** `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`

### `fhir4ds.cql`
**Purpose:** CQL translator and measure evaluator.
**Location:** `fhir4ds/cql/`
**Compliance:** 100% of implemented features pass official CQL compliance.

### `fhir4ds.viewdef`
**Purpose:** SQL-on-FHIR v2 implementation.
**Location:** `fhir4ds/viewdef/`
**Compliance:** 100% compliance with ViewDefinition v2 specification.

---

## Official Compliance Testing

The project maintains a unified conformance suite for validating against official standards.

```bash
# Run all conformance tests (FHIRPath, CQL, ViewDef, DQM)
python3 conformance/scripts/run_all.py
```

Reports are generated in `conformance/reports/`.

### Pytest Plugin Note

`pyproject.toml` intentionally sets `-p no:benchmark` in pytest `addopts`.
The auto-loaded `pytest-benchmark` plugin can hang pytest startup/collection in
this workspace. Do not remove that option unless the plugin issue has been
verified fixed; benchmark runs are handled by the scripts in `benchmarks/`.

### Test Skip / XFail Policy

Do not use `pytest.skip(...)` to hide translator, parser, or generator behavior
that is expected to work. Tests for supported behavior should fail normally.

Use `pytest.mark.xfail(..., raises=ExpectedError)` or an equivalent explicit
expected-error assertion when a spec case is intentionally invalid or a known
gap must remain visible. This keeps XPASS behavior visible when support lands.

Skips are appropriate for environment or fixture availability only, such as a
missing optional DuckDB/C++ extension build, missing external FHIR datasets, or
benchmark/conformance fixture submodules that are not present.

CMS integration tests that need include resolution should use
`fhir4ds/cql/tests/integration/helpers.py::make_cql_library_loader` so included
libraries such as `FHIRHelpers`, `QICoreCommon`, `Status`, `Hospice`, `SDE`,
`AHA`, and `AdultOutpatientEncounters` are exercised instead of skipped.

### Source Adapter SQL Safety

Source adapters must quote identifiers and string literals separately. Use
`quote_identifier()` for DuckDB identifiers and `quote_sql_literal()` for SQL
string literals; never interpolate paths, credentials, secret names, patient ids,
or connection strings directly into SQL. Cloud credential providers and option
keys are allowlisted in `fhir4ds/sources/filesystem.py`; extend that allowlist
deliberately with focused injection tests when adding provider options.

### FHIRDataLoader Ingestion Atomicity

Strict `FHIRDataLoader.load_ndjson(..., strict=True)` must be all-or-nothing for
both malformed JSON and valid-JSON invalid-FHIR records. Parse and validate the
full file before inserting through the batch loader so a later missing
`resourceType`, invalid `id`, non-dict line, or non-standard JSON number cannot
leave earlier rows partially committed. Non-strict NDJSON/directory loading may
skip invalid records with warnings, but strict mode must keep the resources
table unchanged on failure.

Release 0.0.7 Domain 6 fix (2026-05-24): `FHIRDataLoader` custom resource
table names and ValueSet code table names may be valid identifiers that are
also SQL keywords. Store/use the `quote_identifier()` form for all dynamic
table, temp table, and index SQL references; keep the `select`/`where` keyword
regression tests when touching loader SQL generation.

Release 0.0.7 Domain 8 fix (2026-05-24): public JSON-loading boundaries must
validate decoded JSON shape before reading `resourceType`. `FHIRDataLoader`
`load_file()`/`load_from_url()` raise actionable `TypeError` for list/string/null
JSON payloads, directory loading catches those as non-FHIR files, and DQM batch
ValueSet loading raises `DQMConfigError` for non-object ValueSet JSON instead of
leaking `AttributeError`.

---

## Development Workflow
...
- **Benchmarks:** `benchmarks/`
- **Official Tests:** `tests/data/` (Heavy datasets and submodules)

### Release Version Consistency

Release 0.0.7 Domain 10 fix (2026-05-24): package metadata and public
subpackage `__version__` constants must move together. Keep
`pyproject.toml`, `fhir4ds.__version__`, `fhir4ds.cql.__version__`,
`fhir4ds.dqm.__version__`, `fhir4ds.fhirpath.__version__`,
`fhir4ds.fhirpath.duckdb.__version__`, `fhir4ds.viewdef.__version__`, and
notebook install snippets aligned with the release target. Public conformance
facades that emit engine/translator version metadata, such as
`conformance/scripts/run_cql_tests_runner.py`, should read the package version
rather than hardcoding a release string. Guard this with
`fhir4ds/tests/test_version.py`, a generated-metadata smoke check, and a wheel
metadata/import check. Website and WASM release surfaces must move with the
same target: homepage `PRODUCT_VERSION`, website tests, public install
snippets, release notes, `web/wasm-demo/public/` wheel contents, and the copied
`web/website/static/wasm-app/` snapshot. Guard those with the `web/wasm-demo`
build and website typecheck/build.

Release 0.0.9 Domain 10 fix (2026-06-11): release-prep version drift must be
closed across package metadata, all public subpackage `__version__` constants,
notebook install snippets, website version assertions, WASM wheel filename
references, the bundled `web/wasm-demo/public/` wheel, and the copied
`web/website/static/wasm-app/` snapshot. Guard the fix with
`fhir4ds/tests/test_version.py`, wheel metadata/import checks,
`web/wasm-demo` build, and website typecheck/build before marking the release
surface clean.

Release 0.0.11 Domain 10 verification (2026-07-05, HISTORIAN iter-8): clean
install / clean import / binary health verified CLEAN. Candidate wheel
`fhir4ds_v2-0.0.11-py3-none-any.whl` (10,398,155 bytes) ships both native
extensions (`cql.duckdb_extension` 11,249,246 bytes;
`fhirpath.duckdb_extension` 11,567,614 bytes — ELF 64-bit LSB shared object,
x86-64, valid BuildID, linked against libstdc++/libm/libc). All 7 public
`__init__.py` files report `0.0.11` matching `pyproject.toml`. In a fresh
venv with bare `pip install fhir4ds-v2`, `import fhir4ds` succeeds and
`fhir4ds.__version__ == '0.0.11'`; `register(con)` returns
`{'fhirpath_cpp': True, 'cql_cpp': True}`; calling `register(con)` twice
is idempotent. `pip check` is clean. Native C++ path and forced Python
fallback path produce byte-identical output across 9 representative FHIRPath
cases (navigation, `where()`, missing path -> empty, boolean singleton,
equality true/false/empty). Fallback is *never* silent: when forced via
`duckdb.__version__="0.0.0-forced-python-fallback"`, `register()` correctly
returns `{'fhirpath_cpp': False, 'cql_cpp': False}`. Note (not a fhir4ds
bug): `import fhir4ds.dqm` requires `pandas`, which is in the optional
`[measures]` extra because `evaluate_measure` returns DataFrames; top-level
`import fhir4ds` is unaffected.

1. Implementation: `fhir4ds/fhirpath/engine/invocations/`
2. Tests: `fhir4ds/fhirpath/tests/unit/`
3. DuckDB Registration: `fhir4ds/fhirpath/duckdb/udf.py`

### Adding a New CQL Function
1. Translation: `fhir4ds/cql/translator/functions.py`
2. UDF Implementation: `fhir4ds/cql/duckdb/udf/`
3. Registration: `fhir4ds/cql/duckdb/extension.py`

---

## Known Architecture Issues (2026-Q2 Refresh Audit)

See `docs/architecture/AUDIT_REPORT_2026Q2_REFRESH.md` for the full audit report.

### Error Hierarchy
FHIRPath error classes are canonically defined in `fhir4ds/fhirpath/engine/errors.py`.
The DuckDB adapter layer re-exports them from `fhir4ds/fhirpath/duckdb/errors.py`.
**Do not** define new error classes in the DuckDB layer that duplicate core classes.

### Thread Safety
Thread-safety mitigations applied in 2026-Q2 remediation:
- `constants.py` — `Constants()` is per-invocation (already safe; no action needed)
- `TypeInfo.model` — deprecated; never set in production code (documented, planned removal)
- `variable.py` — `_VARIABLE_STORES_LOCK` added for double-checked locking
- `profile_registry.py` — `_default_registry_lock` added for singleton init
- `fhir_loader.py` — `_CACHE_LOCK` added for `WeakKeyDictionary` access
- `fhir_model.py` — `_fhir_model_lock` added for singleton init (2026-Q2 refresh)
- `strings.py` — `_MAX_REGEX_LENGTH` guard added against ReDoS
- `strings.py` — `_REDOS_PATTERNS` detector added for nested quantifiers (2026-Q2 refresh)
- `cql/duckdb/udf/string.py` — same ReDoS guards applied to deprecated CQL UDFs

### CQL Translator Invariants
The 8 architecture invariants documented in `docs/architecture/translator/AGENTS.md`
remain in effect. Post-remediation status (2026-Q2):
- `SQLRaw` mid-pipeline: **20+ sites eliminated** (CQL-001/002/012-016/018-020/025)
- `to_sql()` mid-pipeline: **8 sites fixed** (replaced with proper AST nodes)
- Silent fallbacks: **Fixed** (context.py warns, cte_builder uses registry)
- Strategy 2 templates: **1 active system** (`fluent_functions.py` `body_sql`) — blocked, requires Task C4
- Hardcoded resource types: **Fully externalized** — fallback set in `queries.py` removed, now uses only `schema.resources.keys()`
- Magic strings: `"Measurement Period"`, `"Patient"`, `"Initial Population"` extracted to module constants (`CQL_MEASUREMENT_PERIOD`, `CQL_PATIENT_CONTEXT`, `_DEFAULT_FINAL_DEFINITION`)
- CQL logical precedence: `and` binds tighter than `or`/`xor`, and `or`/`xor`
  share one left-to-right disjunction level; `implies` is lower precedence than
  disjunction. Parser helpers for precision forms such as `day of <expr>` must
  not let the operand absorb a following logical chain, or measure SQL can wrap
  a Boolean expression in temporal helpers such as `intervalStart(...)`. Keep
  direct macro/UDF truth tables and translated query `let`/`where`/`return`
  population SQL parity-tested on native-loaded and forced Python fallback
  DuckDB registrations.
- CQL logical operators are Boolean-only at the translator boundary. Statically
  known non-Boolean literals, lists, and typed definition aliases must raise a
  translation error for `and`, `or`, `xor`, `implies`, and unary `not` instead
  of relying on DuckDB numeric/string truthiness. Parser-internal `between ...
  and ...` bounds are the exception: lower `between` before validating logical
  operands so the separator `and` is not treated as a predicate.
  Public direct logical macros must also guard their operands instead of
  inheriting DuckDB truthiness, and no-Python/browser-style `logicalImplies`
  must return SQL NULL for malformed Boolean text such as `'yes'`. Static
  logical validation must classify clinical and complex operands (`Code`,
  `Concept`, `Quantity`, `Interval`, `Tuple`) and typed parameters before SQL
  generation so structured non-Boolean values cannot reach raw SQL `AND`/`OR`.
  CQL-04 HISTORIAN fresh rerun added two more guardrails: `as Any` /
  `as System.Any` must not erase a statically known non-Boolean source before
  logical validation, and Patient-context `singleton from (query)` count/value
  subqueries must remain correlated to `_pt.patient_id` so query
  `let`/`where`/`return` logic cannot mix patients.
  CQL-04 EXPLORER found the same erasure risk through `convert ... to Any` and
  non-Boolean function results hidden by `as Any`. Logical operand inference
  must classify CQL conversion/function return types such as `ToString`,
  `ToInteger`, `ToQuantity`, `ToConcept`, temporal constructors, and
  `ConvertsTo*` before SQL generation; only Boolean-returning functions may
  flow into `and`, `or`, `xor`, `implies`, or unary `not`.
- CQL comparison operators must dispatch through semantic operator paths before
  lowering to SQL. `between` is equivalent to `>=` and `<=`, so Quantity,
  temporal, and dynamic FHIR operands must still reach the unit-aware and
  precision-aware comparison helpers. Generic `~`/`!~` must not fall back to
  raw SQL equality for strings, lists, or tuples; use CQL equivalence semantics
  including case/whitespace normalization and element-wise equivalence.
  CQL-18 HISTORIAN relaunch doctrine (2026-08-22): CTE defines have TWO
  physical list shapes that share the inferred CQL type List<T>: (a)
  stored-list defines (static list literals, and dynamic multi-valued
  property defines like `define G: Patient.name.given`, promoted via
  _promote_fhirpath_text_list at define time) whose value column holds the
  WHOLE element list in one row, and (b) query-produced defines
  (`define Q: (from {1,2,3} X return X)`) which are List<Integer> but do
  NOT store a list value. `DefinitionMeta.stores_list_value` is the single
  discriminator — never gate list consumers on `List<` cql_type alone.
  Stored-list consumers: Count/Sum/Min/Max/Avg aggregate over the stored
  list (_translate_aggregate_pre), IndexOf skips the rows-to-list wrap,
  First/Last LIST_EXTRACT the stored list (pre-translate). Dynamic-list
  defines are PATIENT_SCALAR + List<Any>. Both-dynamic
  `includes`/`included in` operands are promoted to list projections before
  the _is_list_operands gate (interval-guarded). First/Last over a static
  String raise a typed TranslationError (§10.8/§10.9 have no String
  overload; LIST_EXTRACT over VARCHAR silently slices characters — was
  First('final')→'f'). Multi-valued navigation over a retrieve define
  (O.component, O.component.code.coding.code) collapses to one dotted path
  via _resource_rows_navigation and aggregates
  flatten(LIST(from_json(fhirpath(...)))) per patient when any path segment
  is 0..* per FHIRSchemaRegistry.is_multi_valued_element (prefix-walked
  cardinality; schema element table only stores ~3 levels). NOT A BUG:
  `O.component.code.code` navigates a nonexistent `code` child of
  CodeableConcept — empty/false is spec-correct FHIRPath behavior; the valid
  path is component.code.coding.code. `_is_list_operands` recognizes
  _is_list_returning_sql operands (from_json list projections, LIST()
  subqueries) so list SQL never falls into interval dispatch.
  CQL-18 EXPLORER relaunch doctrine (2026-08-22): (1) deep multi-valued
  navigation defines (`define CC: Obs.component.code.coding.code`) are
  PATIENT_SCALAR stored-list CTEs via the `stores_patient_list` marker set in
  _resource_rows_navigation — the PATIENT_MULTI_VALUE wrap drops the outer
  patient correlation and produces an invalid GROUP BY; (2) `stores_list_value`
  is ALSO inferred from the translated SQL shape
  (_definition_result_is_list_returning) for alias-of-list-op defines
  (`define A2: distinct A_Lit`) — AST/List<-typing alone missed depth-2
  aliases (First(A2) returned the whole list); (3) includes/included-in
  singleton overload must route to the contains macro (null elements equal);
  list-list typed-null operands return SQLNull at the expression level — the
  Boolean-define population boundary flattens null→false by presence-encoding
  (INTENDED; verify null via non-Boolean contexts like `{ (expr) }`);
  (4) inline chained list operators require `_is_single_list_expr` to
  recognize list-producing SQL (set-op macros, flatten, list_value,
  list_slice) and `_promote_list_setop_scalar_operands` to promote scalar
  operands beside list operands to singleton lists (App B list promotion);
  (5) heterogeneous String/numeric/Boolean list literals raise a typed
  TranslationError at translate time (_validate_list_selector_common_type);
  int+Decimal mixing stays legal (common Decimal supertype).
  CQL-10 re-launch doctrine (2026-08-21): High/LowBoundary Decimal semantics
  follow the HL7 reference implementation (append 99999999/00000000 then
  setScale(precision, DOWN)) — HighBoundary(1.587,2)=1.58 even though v2 spec
  prose says 1.59; fixtures/reference outrank prose. Ceiling/Floor return
  Integer with null beyond Integer extent; Exp/Ln/Log return scale-8 Decimal;
  mixed Integer+Long arithmetic promotes to BIGINT (Long literals inside INT32
  range otherwise lose typing and raise INT32 OutOfRangeError).
  CQL-10 HISTORIAN FIX doctrine (2026-08-21): Decimal boundary results are
  exact-Decimal end-to-end — the translator transports High/LowBoundary via
  VARCHAR→DECIMAL(38,8) (never DOUBLE), and the Python UDFs
  (`udf/math.py` highBoundary/lowBoundary) return exact boundary TEXT for
  DECIMAL-typed inputs (matching the native extension's string contract);
  any `float()` round-trip corrupts >15-significant-digit values and breaks
  the official LowBoundaryDecimal scale-8 rendering (1.58700000). Statically
  String/Boolean operands for the arithmetic family (Abs/Ceiling/Floor/Exp/
  Ln/Log/High/LowBoundary and binary `/ ^ * -`) raise a uniform typed
  TranslationError via `_validate_static_arithmetic_operands` /
  `_operators.py` static guard; null/Any/dynamic operands pass through to
  runtime null semantics. Validation harness trap: probe scripts under
  `.temp/` run with sys.path[0]=script dir, so `fhir4ds` resolves from
  site-packages — always validate with `PYTHONPATH=/mnt/d/fhir4ds`.
  CQL-09 SKEPTIC doctrine (2026-08-21): composite EQUALITY must preserve
  uncertainty — `{1, null} = {1, 2}` is null (null-null list elements are
  equal, one-sided null elements are uncertain), and interval equality via
  Start/End treats a one-sided CLOSED null bound (`Interval[1, null]`) as
  unknown (null) while a one-sided OPEN null bound (`Interval[1, null)`) is
  unbounded (false). The null-element CASE lives inside
  `CQLListEqualEq`/`CQLListEqualTemporalEq` only; `CQLListElementEqual`
  keeps one-sided null → FALSE because `in`/`contains`/`except`/`distinct`
  pin the not-contained doctrine. Dual-engine: `Interval::equals_nullable`
  (interval.cpp) and `_interval_bound_equals_nullable` (udf/interval.py)
  must stay in lockstep; rebuild + deploy the cql.duckdb_extension after
  native edits. NOT A BUG (spec erratum): CQL 1.5 examples
  `ListNotEqualIsNull` and `DateTimeWithMillisecondsEqualIsNull` contradict
  the normative algorithm text (and `ListEqualIsTrue`); the implementation
  follows the algorithm (`{null,1,2,3} != {null,1,2,3}` is false under
  not(=true); day-precision mismatch is false even when ms precision is
  absent). Also verified conformant and NOT to be "fixed": exact-Decimal
  `0.1 + 0.2 = 0.3` is true; `3.5 'cm2' != 3.5 'cm'` is null while
  `!~` is true; `1 !~ '1'` is true (~ of type mismatch is false).
  CQL-09 HISTORIAN doctrine (2026-08-21): composite list ELEMENTS must also
  preserve uncertainty — `{{1, null}, {2}} = {{1, 2}, {2}}` is null (nested
  list elements recurse into list equality) and `{Tuple {a: 1, b: null}} =
  {Tuple {a: 1, b: 2}}` is null (tuple elements compare field-wise with `=`).
  Implemented in `macros/list.py` via `CQLNestedListEq{Elem,Temporal}` +
  `CQLJsonEq{Elem,Temporal}` (JSON[]-normalized, subquery-free so they are
  lambda-legal) and `CQLTupleValueEqual` (json_each field-wise 3VL) wired into
  the `CQLListEqual{Eq,TemporalEq}` element CASE and `CQLListElementEqual`.
  DuckDB constraints that shaped the design: macros cannot recurse (syntactic
  expansion), correlated UNNEST and subqueries-in-lambdas are unsupported, and
  `range()` is half-open with BIGINT args. Documented boundary: nested
  clinical/quantity/interval JSON objects at depth >= 2 and lists nested
  deeper than 2 levels compare uncertainty-preserving (equal-shape TRUE else
  NULL), never definitely-wrong. Numeric JSON leaves compare via
  DECIMAL(38,8) so `1.0` vs `1` is TRUE across json_type DOUBLE/UBIGINT.
  NOT A BUG: `Code { code: null, system: 's' } =` same → true — §9.4 Equal
  does not define Code equality (only ~ does); consistent with the pinned
  CQL-02 absent==explicit-null doctrine. Conformant (do not "fix"):
  `@2012-01-01T12:00 < @2012-01-01T12:00:00` → null (one side lacks seconds
  precision); `-1 'm' < 1 'cm'` → true (unit-aware −100 cm < 1 cm).
  CQL-09 EXPLORER doctrine (2026-08-21): bare numeric literals vs STATIC
  Quantity literals promote to unit-'1' quantities (CQL 1.5 Table 9-E) and
  compare unit-aware in `_operators.py` — `1 = 1 'm'`/`1 < 2 'm'` → null
  (§9.5), `1 ~ 1 'm'` → false, `1 !~ 1 'm'` → true (§9.7 never null; was a
  BinderException), `1 = 1 '1'` → true. DYNAMIC FHIR quantities vs bare
  numerics intentionally keep the numeric path: FHIRHelpers unit
  `Coalesce(code, unit, '1')` admits non-UCUM display strings (CMS72
  fixtures carry `unit: "0"` with no code) and official eCQM fixtures pin
  numeric comparison (`INR.value as Quantity > 3.5`); a global promotion
  regressed CMS72/CMS190 by one patient each. Stale doctrine corrected:
  `5 'mg' = 5` is now null (was pinned True). Equivalent (~) on temporals
  at differing precision → false (not null); seconds+milliseconds are one
  combined decimal precision; offsets compare as instants. Code/Concept
  ordered comparisons → null (§9.10 type list); `true > false` → true
  (unspecified, FHIRPath-consistent). Deferred: UCUM-validity-gated numeric
  fallback inside `quantity_compare` (dual-engine) to extend the promotion
  to dynamic quantities.
  CQL-11 SKEPTIC doctrine (2026-08-21): TruncatedDivide (`div`) must lower
  through the exact `cqlDivide` core + `TRUNC` + typed `TRY_CAST`
  (INTEGER/BIGINT for Integer/Long operand pairs, DECIMAL(38,8) core for
  Decimal/dynamic) — never DuckDB's DOUBLE `/` promotion, which made
  `0.3 div 0.1` → 2 (spec 3) and lost Long-range exactness/overflow-to-null.
  `mathPower` (python udf/math.py AND native cql/math.cpp math_power) must
  emit sub-1e-4 magnitudes in fixed `%.8f` notation: DuckDB's
  VARCHAR→DECIMAL(38,8) cast rounds scientific text like '9.09e-10' UP to
  1E-8, so Power(2,-30) must return 0.00000000, not 0.00000001 (native
  rebuild + md5-verified deploy required after the C++ edit).
  `Precision` numeric literals (Integer/Long, not just Decimal raw_str) must
  reach `CQLPrecision` as VARCHAR text — a raw INTEGER literal raises a
  native BinderException while the Python path duck-types it to 0.
  CQL-14 EXPLORER doctrine (2026-08-21): timing-phrase qualifiers follow the
  CQL 1.5 grammar `'same' dateTimePrecision? (relativeQualifier|'as')` — the
  parser must never consume a token assuming `as` (it silently rewrote
  `starts same day or after` to same-as equality, and `starts same or after`
  ParseError'd), and `_translate_tail_operators`'s `" or " in operator`
  prefix heuristic must not route the same-family into quantity-offset
  semantics. `starts/ends on or before|after <prec> of X` must compare BOTH
  bounds at the specified precision via cqlSameOrBeforeP/cqlSameOrAfterP —
  never hardcoded DATE casts (false negatives at year/month). NOT A BUG:
  `qualifier same <prec> as Interval[...]` is SameAs(bound, interval-as-
  singleton) per reference cql-to-elm (start AND end must match; right bound
  only reduced by explicit trailing `start of`/`end of`); `Today() <= Now()`
  → null is implicit-conversion precision uncertainty; DateTime − DateTime
  has no Subtract signature (use duration between).
- Dynamic FHIR choice values compared to numeric literals must use
  `fhirpath_number`, not `fhirpath_text` plus `TRY_CAST`; a `valueString` of
  `"5"` is not numeric evidence. Dynamic `Observation.value` Quantity
  comparisons against static CQL quantities should first route JSON Quantity
  values through `parse_quantity`/`quantity_compare`, with primitive numeric
  fallback only for non-Quantity choices. Retrieve/precomputed-column
  optimization must preserve these guards: do not replace `fhirpath_number`
  with a non-numeric precomputed column, and cast optimizer-created scalar
  subqueries before numeric literal comparisons.
- Dynamic FHIR choice values used in arithmetic must follow the same numeric
  discipline: `value`/`value.*` paths use `fhirpath_number`, not
  `fhirpath_text` plus `TRY_CAST`, and untyped Quantity choices must not be
  silently reduced to scalar numbers. CQL `+` must not fall into string
  concatenation when either operand is numerically typed. Quantity plus/minus a
  scalar is not date arithmetic; return NULL for definitely non-temporal peers
  while preserving date/time plus time-valued Quantity for temporal and
  aggregate/query-derived expressions.

### CQL Primitive Type and Conversion Boundaries
`System.Any` is the maximal CQL supertype; `x is Any` must lower to a non-null
test and must not fall through to FHIR resource-type JSON extraction for
primitive values. Integer and Long literals must enforce their CQL ranges,
including signed minima represented as unary negation. Decimal literal SQL must
preserve authored precision when the parser kept `raw_str`.

CQL-01 SKEPTIC found two primitive lexical fragility points. The CQL string
escape table includes `\/` and ``\` ``; those must decode to `/` and backtick
instead of preserving the backslash. Long literals use the uppercase `L` suffix
from the official `LONGNUMBER` grammar; lowercase `l` after digits is invalid
numeric-suffix junk and must not tokenize as `Long`.

CQL-01 HISTORIAN found that scalar primitive parameters must preserve both
compile-time defaults and declared CQL type metadata. Do not lower
`parameter P Integer default 5` or supplied scalar bindings to an untyped
`getvariable()` VARCHAR path before primitive `is`/`as` or arithmetic; defaults
should compile as typed SQL expressions and required runtime scalar parameters
should be cast according to their declared primitive type.

CQL-01 HISTORIAN (2nd pass, 2026-08-19) found numeric-semantics traps on the
primitive arithmetic/aggregate surface. (1) Scalar `/` must lower to the
exact `cqlDivide` UDF (macros/math.py): DuckDB's native `/` ALWAYS promotes
DECIMAL operands to DOUBLE (9.9 / 3.0 -> 3.3000000000000003), and exact
base-10 division is inexpressible in DuckDB SQL. (2) List `Sum` must use
DuckDB's native exact list sum (HUGEINT / DECIMAL(38,8)) with TRY_CAST to
INTEGER/BIGINT for integral element types — never the DOUBLE
list_transform path (Sum({maximum Long, 1}) must overflow to null, not
silently lose precision). `Avg` = cqlDivide(exact_sum, non-null count).
(3) HAZARD: any expression newly returning DECIMAL(38,8) breaks DuckDB
COALESCE/CASE sites that mix it with VARCHAR dynamic FHIR values (binder
error, regressed 7 DQM measures) — extend `_translate_coalesce`'s
`_is_numeric_expr` when adding DECIMAL-returning surfaces. (4)
`maximum/minimum T` FunctionRefs carry their result type via a bare
Identifier arg; `_function_return_type` resolves both Identifier and
NamedTypeSpecifier forms.

CQL-01 EXPLORER found a fragile `Any` materialization boundary. Scalar
primitive definitions asserted `as Any` or `as System.Any` must remain
patient-scalar `value` projections in `definition_meta`; final population SQL
must not reclassify them as resource-shaped CTEs and select `.resource`.

CQL-01 EXPLORER fresh rerun (2026-08-19, spec-compliance campaign) fixed the
definition-alias numeric arithmetic boundary in
`fhir4ds/cql/translator/expressions/_operators.py`. When an arithmetic operand
is a definition-alias scalar subquery `(SELECT sub.value FROM "CTE" ...)` and
the other operand is numeric, the old code forced `TRY_CAST(... AS DOUBLE)`,
which (1) broke exact Decimal semantics through alias chains (`define N: M +
0.2` → 0.30000000000000004) and (2) promoted Integer/Long alias values to
DOUBLE so the CQL overflow-to-null rule could not fire (`define I:
2147483647; I + 1` → 2147483648.0). The cast is now driven by
`definition_meta[cte].cql_type`: Decimal → `DECIMAL(28,8)` (spec-exact
20+8 digits); Integer/Long compute in `DECIMAL(38,0)` and the result is
narrowed with `TRY_CAST` back to INTEGER/BIGINT so overflow yields NULL
(DuckDB rejects `TRY()` around scalar subqueries, so the literal path's
TRY-wrap cannot be reused here). Unknown-typed subqueries keep the DOUBLE
fallback. Covered by `TestDefineAliasArithmeticExactness` in
`fhir4ds/cql/tests/unit/test_cql01_primitive_types.py`.

CQL-08 EXPLORER doctrine (2026-08-21): query-valued `is (not) null` is
EXISTENTIAL (row presence over the lowered subquery), NOT the strict-spec
List-never-null constant — official eCQM content (CMS2/CMS771/CMS130 use
`( "Most Recent X" Q where ... ) is not null` as a non-emptiness test) and
the DQM fixtures encode that expectation; constant-folding per Appendix B
prose regressed DQM 47→41 and was reverted. Literal-list path stays
strict-spec: IsNull({})=false, IsNull({null})=false, IsNull(null as
List<T>)=true. Pinned in test_nullological_parity.py. Also found (deferred,
QA-003): a query alias colliding with a library define name mis-resolves
(define D + `from {} D return D` emits `FROM "D"` — Catalog Error). Coalesce temporal-family note: Date and
DateTime share one partial-precision ISO string space (ToDateTime(Date) is
identity), so a Date value selected from a mixed Date/DateTime Coalesce is
runtime-identical to its DateTime promotion — representation only, NOT A BUG.
Division-by-zero nulls feed Coalesce correctly on both engines
(Coalesce(P.multipleBirthInteger / 0, 42) -> 42 through real retrieves).

CQL-08 nullological doctrine (SKEPTIC, 2026-08-20): CQL 1.5 §Coalesce is
variadic with NO upper bound — the former 2..5 scalar-arity cap (translator
`_translate_coalesce` and public UDF `Coalesce` in `udf/logical.py`) was a
spec violation and is removed; `<2` scalar args still rejects (single-arg is
the Appendix B `List<T>` overload). Coalesce static operands mixing
String-family with Integer/Long/Decimal now raise a uniform TranslationError
in either order (spec: arguments implicitly castable to a common type;
DuckDB's COALESCE binder was order-dependent). NOT A BUG registry:
IsTrue/IsFalse on non-Boolean operands return false (never null, no SQL
truthiness — pinned by test_cql_infix_is_true_false_rejects_sql_truthiness);
the `IsNotNull` function macro is a harmless superset of the spec's
`is not null` operator form. Expression-level Coalesce(all-null) defines stay
NULL — only population membership SQL applies the CQL-04 null→FALSE encoding.

CQL-08 addenda (HISTORIAN, 2026-08-20): (1) The Coalesce static type-family
guard now propagates through nesting — `_infer_static_cql_type_for_logical_operand`
infers a `coalesce` FunctionRef's return type from its first non-Any argument
(spec: common type of the arguments), so `Coalesce(1, Coalesce(null,'a'))`
raises the same typed TranslationError as the flat form instead of leaking a
raw DuckDB binder error at execution. (2) DOCTRINE CORRECTION superseding the
CQL-07 master "Decimal converts by truncation" claim: CQL 1.5 Appendix B
Table 9-E defines NO Decimal→Integer/Long conversion and `ToInteger` has no
Decimal overload (Boolean/String/Long only; verified live against cql.hl7.org,
verbatim Table 9-E Decimal row). `ToInteger(Decimal)`/`ToLong(Decimal)` → null
and `ConvertsToInteger/Long(Decimal)`/`CanConvert(Decimal, Integer/Long)` →
false, on both native and python surfaces; explicit truncation is the separate
`Truncate` operator. Guarded by
`test_cql_to_integer_long_reject_decimal_cql08_historian`. (3) QuantityToString
calendar-keyword pin: `convert 38 'weeks' to String` renders `38 weeks`
(calendar-duration keyword bare, per the CQL-06 macro doctrine); UCUM units
stay quoted (`37 'cm'`).

NOT A BUG (CQL-01 EXPLORER, 2026-08-19): out-of-extent Decimal literals
(beyond the `(10^28-1)/10^8` maximum-Decimal prose, up to 28 integer digits)
are intentionally accepted at translation. The official
ValueLiteralsAndSelectors.xml fixtures pin 28-int-digit literals as VALID;
official fixtures outrank the prose (a stricter extent check regressed 3
official CQL tests to 1703/1706 and was reverted). The parser's existing
boundary (parser.py:1596: ≤28 integer digits, 29+ raises) is the
fixture-compatible policy. Also spec-correct: `ConvertsToBoolean('yes')` is
true — CQL 1.5 Table 9-F lists true/t/yes/y/1 and false/f/no/n/0,
case-insensitive.

CQL string-to-Integer/Long conversion accepts only the integer string grammar
`^[+-]?[0-9]+$`. Decimal-looking strings such as `"1.0"` and `"1.5"` return
null/false for `ToInteger`/`ConvertsToInteger` and `ToLong`/`ConvertsToLong`
rather than rounding or throwing. `ToInteger`, `ToDecimal`, `ToBoolean`, and
`convert ... to <primitive>` must route through the spec-aware DuckDB
macro/UDF surface rather than generic DuckDB `TRY_CAST`; invalid conversions
return NULL/false and must not raise. Keep the native-loaded DuckDB connection
and forced Python fallback connection parity-tested for these public functions.

CQL primitive `as` is a type assertion, not a conversion. Matching primitive
types return the original value, `as Any` returns any non-null input, and
mismatched primitive assertions such as `5 as String`, `'5' as Integer`, or
`true as Integer` must translate/execute as SQL NULL. Dynamic FHIR or measure
value expressions may be physically `VARCHAR`; primitive `as` over those values
must use shape guards plus `TRY_CAST` so matching runtime values become typed
SQL results for downstream arithmetic while mismatches remain NULL. For direct
FHIR choice values, SQL text shape is not type evidence: use FHIRPath
`type().name` to distinguish `valueInteger` from `valueString`. For
materialized primitive definitions, preserve/infer `definition_meta.cql_type`
and use that metadata for `is`/`as` instead of reclassifying all projected
values as strings.

CQL-05 HISTORIAN confirmed the `cast X as T` prefix is distinct from nullable
`X as T`. The parser should preserve `BinaryExpression.strict=True` for
`cast`, and translated strict casts must evaluate the same type predicate used
by `is T`: matching values pass through, while mismatches raise a
`CQL strict cast failed` DuckDB runtime error instead of returning SQL NULL.
Keep this separate from `as`, which remains a null-returning type assertion.
CQL-05 EXPLORER added that function inlining/substitution must preserve the
same `BinaryExpression.strict` flag; otherwise `define function F(x Any): cast
x as String` silently degrades to nullable `as` after inlining.

The CQL lexer must reject no-whitespace junk after numeric literals, including
`1LL`, `1.0L`, and `1day`. Whitespace-separated tokens are parsed by the query
grammar and should be evaluated there, not treated as numeric suffixes.

### CQL Clinical Type Boundaries
CQL Code selectors and named code references must preserve CQL Code shape as
JSON values with `code`, `system`, and optional `display`; do not lower new
paths to the legacy `system|code` string form. `ToConcept()`, clinical `is`,
and clinical `as` depend on that shape in both native-loaded DuckDB and forced
Python fallback execution.

Clinical operator implementation is a fragile area for CQL-21: keep all
Age/AgeAt/CalculateAge/CalculateAgeAt precision variants registered and
translator-routed consistently, including weeks/hours/minutes/seconds. Static
Code/Concept membership in CodeSystem/ValueSet and ExpandValueSet must not be
treated as generic SQL `IN` or resource-path `in_valueset` calls over clinical
JSON; preserve CQL clinical equality/equivalence semantics at those boundaries.
CQL-21 SKEPTIC remediation added regression coverage in
`fhir4ds/cql/duckdb/tests/integration/test_clinical_operator_parity.py`; extend
that parity file whenever adding clinical operator surfaces.

CQL-21 HISTORIAN launch (2026-08-23) closed the remaining §22.21 VARCHAR
consumers: uncertainty-capable operands (age family, cqlDurationBetween)
must never reach CQLListContainsEq, list_min/list_max, LEAST/GREATEST, or
SQL unary minus unprepared. `age in {literal list}` lowers to an OR chain
of `cqlUncertainCompare(x, e, '=')`; unary negation lowers to
`cqlUncertainMultiply(x, '-1')` (the old cqlDurationBetween-only BIGINT
cast silently NULLed uncertain ranges and was removed); scalar and list
Min/Max lower through `cqlUncertainMin/Max` and
`cqlUncertainListMin/ListMax` (interval-aware: Min = [min of lows, min of
highs], Max = [max of lows, max of highs]; nulls ignored; crisp
collapses). All are dual-engine (Python `udf/datetime.py` + native
`cql_extension.cpp`). Known limitation (LOW, deferred): uncertain elements
inside DYNAMIC (non-literal) lists still lower to CQLListContainsEq.
Deployment hazard observed twice now: site-packages
`cql.duckdb_extension` can silently revert to a stale binary between
sessions — verify md5 parity (build == repo bundle == site-packages) at
launch start, not only after a rebuild.

CQL-21 EXPLORER fixed the same fragility for dynamic FHIR clinical values:
resource-backed expressions such as `O.code in LOINC` must not fall through to
generic SQL `IN` against the structured CodeSystem literal. They now lower to a
resource/path CodeSystem membership predicate. Keep native/Python fallback
parity coverage for both direct dynamic paths and `as Concept` dynamic paths.

`ExpandValueSet(ValueSet)` is list-returning. Translated CQL chains such as
`Count(ExpandValueSet(VS))` must count expanded Code elements in both
native-loaded and forced Python fallback registrations. Raw direct DuckDB
`Count(...)` currently remains DuckDB's row aggregate; do not shadow it with a
macro unless `COUNT(DISTINCT ...)`, `FILTER`, window, and row-aggregate syntax
remain intact.

ValueSet and CodeSystem references must preserve structured clinical value
shape in value/type contexts (`id`, `name`, and optional `version`) and
definition metadata must keep their clinical CQL type. Terminology membership
boundaries are the exception: before calling `in_valueset`, unwrap structured
ValueSet JSON back to the canonical URL, including function-inlined parameters
and fluent builders such as `hasPrincipalDiagnosisOf` and
`hasPrincipalProcedureOf`.

`Code` and `Concept` are distinct clinical types and are not `Vocabulary`.
`Vocabulary` is satisfied by `ValueSet` and `CodeSystem` only. Clinical `as` is
a type assertion, not a conversion: exact matches pass through, `Vocabulary`
accepts `ValueSet`/`CodeSystem`, and mismatches such as `Code as Concept` or
`ValueSet as CodeSystem` must return SQL NULL.

CQL-02 SKEPTIC found three clinical-type regression traps: declared clinical
parameter types must feed the same static `is`/`as` path as definition metadata;
`ToConcept(Code)` propagates `Code.display` to `Concept.display` and rejects
non-Code JSON shapes such as Quantity; and `ToConcept(List<Code>)` must route to
a list-aware helper/overload rather than `ToConcept(VARCHAR[])` binder errors.
Static null Code/String/Concept membership in ValueSet or CodeSystem returns
false, not SQL NULL or generic `IN` SQL.
CQL-02 HISTORIAN rerun found the ValueSet `codesystems { ... }` declaration
clause was missing. The CQL parser must accept one or more CodeSystem
identifiers after a ValueSet id/version, reject empty or trailing-comma override
lists, and preserve those overrides as structured `codesystems` entries in the
runtime `System.ValueSet` JSON using the referenced CodeSystem id/name/version.
CQL-02 EXPLORER found clinical assertion chains can erase concrete value shape
if only the asserted supertype is tracked. `ValueSet as Vocabulary` and
`CodeSystem as Vocabulary` must still satisfy downstream `is ValueSet` /
`is CodeSystem` and `as ValueSet` / `as CodeSystem`, because the runtime value
remains the original concrete subtype. Clinical aliases through `as Any` should
inline static Code/Concept/ValueSet/CodeSystem definitions for direct
translation instead of generating standalone patient-correlated CTE lookups.
Static Concept instance equivalence must read `Concept { codes: { ... } }`
lists and compare by Code system+code intersection, not route Concept JSON
through FHIR resource-path predicates.
CQL-02 EXPLORER fresh rerun (2026-06-30) found that clinical equivalence
(`~`/`!~`) and clinical equality (`=`/`!=`) over **top-level define aliases
wrapping inline clinical literals** (e.g., `define C: Code 'x' from CS`
followed by `define Test: C ~ Concept { codes: { ... } }`) was not folded at
translation time. The `_static_clinical_value_object` and `_resolve_code_ref`
helpers in `fhir4ds/cql/translator/expressions/_operators.py` only consulted
`context.get_code` (which sees named `code`/`concept` DECLARATIONS), not
`context.expression_definitions` (which stores top-level define bodies). With
no static value resolved, the translator emitted a generic SQL CASE whose
final ELSE arm was raw JSON string equality, comparing a Code JSON shape
(`{"code":...,"system":...}`) against a Concept JSON shape
(`{"codes":[...]}`) which always evaluates to False. Both helpers now fall
back to `self._definition_source_ast(name, node)` and recurse on the
definition's CQL AST when `get_code` returns None. The fix is general — it
covers any top-level define whose body is a CodeSelector or Concept
InstanceExpression, including through `QualifiedIdentifier` (library-qualified
define references). Regression coverage in
`test_clinical_type_parity.py::test_cql_clinical_equivalence_folds_define_alias_operands_cql02_explorer`.
Keep this parity-tested on native-loaded and forced Python fallback
registrations.

CQL-02 SKEPTIC fresh rerun (2026-08-19, spec-compliance campaign) found four
clinical-type spec divergences, all shared by Python fallback and native C++
(translator-layer): (1) Code/Concept `~` compares code+system case-SENSITIVELY
(`_code_key` in `_operators.py::_translate_equivalence_op`) although spec defines
Code equivalence via String equivalence (case-insensitive, whitespace-normalized);
(2) `Concept { codes: { "NamedCode", ... } }` double-serializes named-code members
as JSON strings inside the codes list (generic instance path in
`_lists.py::_translate_instance_expression`), so `Count((...).codes)` sees 1 element
for 2 codes; (3) the `.codes` accessor on Concept values lowers to
`fhirpath_text(<concept>, 'codes')` returning ONE code instead of List<Code>
(`Count(concept.codes)` → 0); (4) a top-level define of a static clinical literal
referenced by alias emits a patient-correlated subquery against a patient-id-less
CTE (`(SELECT sub.value FROM "CodeDef" ... WHERE sub.patient_id = _pt.patient_id)`
while the CTE is `AS (SELECT '<literal>')`) — Binder error end-to-end; the same
shape mismatch pre-exists for String/Integer literal defines. Static
Code-in-CodeSystem membership remains structural (system match, no expansion) —
intended gap without terminology data. Probe:
`.temp/qa/cql02_skeptic_fresh_probe.py`.

All four were RESOLVED in the same launch (CLEAN exit, conformance
2832/2832): (1) `_cql_string_equivalence_key` (casefold + whitespace
normalize) now feeds `_code_key` in `_translate_equivalence_op`; (2)
`_fold_static_concept_instance` in `_translate_instance_expression` builds
structured Concept JSON for statically resolvable members; (3)
`_fold_static_clinical_property` (in `_translate_property`) folds
`.code/.system/.version/.display/.codes` on static clinical values —
`.codes` emits a SQLArray List<Code> so `Count(concept.codes)` works, and
`_static_clinical_value_object` folds ToConcept(Code)/ToConcept(List<Code>);
(4) static clinical literal defines inline at a single choke point at the
top of `_translate_identifier` (helper `_is_static_clinical_definition`,
recursive through clinical define chains). Regression coverage: four new
dual-backend `test_cql02_skeptic_*` tests in
`fhir4ds/cql/duckdb/tests/integration/test_clinical_type_parity.py`
(including full-pipeline `translate_library_to_sql` execution). Followup
(out of chunk): generic String/Integer literal defines referenced by alias
still Binder-error (`define S: 'hello'; define T: S`) — same
patient-id-less CTE shape mismatch, CQL primitives scope. Two stale test
expectations contradicting CQL-01 doctrine were also repaired
(test_aggregate_parity avg/tolerance; test_primitive_parity ToDecimal
rounding).

CQL-02 HISTORIAN fresh rerun (2026-08-19, spec-compliance campaign) found
three more clinical-vocabulary boundary divergences and re-verified all
CQL-02 SKEPTIC fixes intact: (1) `X in VSDef` / `X in CSDef` where the
operand is a define alias of a ValueSet/CodeSystem declaration emitted the
structured clinical JSON as a raw SQL IN-list operand (`... IN
'{"id":...}'` ParserException on BOTH backends) — `_resolve_valueset_identifier`
now follows Identifier/QualifiedIdentifier define-alias chains through
`_definition_source_ast` (depth-capped) and a new
`_resolve_codesystem_identifier` applies the same discipline to the
codesystem membership branch; (2) `Concept { }` (empty concept selector, no
`codes` element) fell through `_code_entries_from_ast` to the generic
membership path emitting invalid `json_object() IN '<JSON>'` SQL — an empty
Concept now folds to an empty code-entry list so `Concept { } in VS/CS`
folds to FALSE, while a present-but-unparsed `codes` element still defers
to runtime; (3) the Python-fallback placeholder `in_valueset` UDF
(fhir4ds/cql/duckdb/extension.py) RAISED `InvalidInputException` through
DuckDB when no valueset data was loaded while native C++ returns SQL NULL —
it now returns NULL with a warn-once guidance log. `ExpandValueSet` was
verified already JSON-unwrap-capable at the macro boundary. Also verified
clean: versioned `code X: 'c' from CS version 'v'` selectors, CodeSystem
tuple equality (same-id-different-name → false), Concept codes-order
sensitivity for `=` vs order/case-insensitive intersection for `~`, and
List<Code>/List<Concept> case-insensitive equivalence transport. Four new
`test_cql02_historian_*` dual-backend tests added to
`fhir4ds/cql/duckdb/tests/integration/test_clinical_type_parity.py`.
Three stale CQL-01-era test expectations repaired
(test_arithmetic_operator_parity cqlDivide,
test_arithmetic_part2_parity CAST(min/max AS INTEGER),
test_nullological_parity Decimal division).

CQL-02 EXPLORER fresh rerun (2026-08-19, spec-compliance campaign) found two
more translator-layer clinical-type divergences, shared by both backends, and
re-verified the SKEPTIC/HISTORIAN fixes intact: (1) an ABSENT Code element and
an explicit `null` element folded differently (`Code { code: 'x' } ~ Code
{ code: 'x', system: null }` returned False; spec: both are "no value" —
null ~ null is true and null is not equivalent to '').
`_normalize_static_clinical_code` now elides null-valued elements so absent ==
explicit null, and value-vs-null falls into the existing key-set-mismatch
SQLNull branch (tuple equality is a conjunction of equality comparisons);
a shared null-aware `_code_equivalence_key` now feeds `_code_key` in
`_translate_equivalence_op`. (2) `(Concept {...}).codes ~ <List<Code>>` (also
via `ToConcept(...).codes` and define aliases) fell through to
`CQLListEquivalentEq`, which compares Code JSON byte-wise (case-sensitive),
because `_translate_list_equivalence` requires ListExpression on both sides;
a new `_static_code_list` resolves statically-known List<Code> operands and
`_translate_equivalence_op` folds them to element-wise Code equivalence with
a length check. Do NOT extend `_static_code_list` to bare Concept operands:
Concept `~` is code-INTERSECTION (order-insensitive) while List<Code> `~` is
ordered element-wise equivalence — both semantics are load-bearing and
parity-tested. Boundary matrix verified clean: unicode/casefold (ß~SS),
tab/space/leading/trailing whitespace in code and system for `~` (and
case-sensitive for `=`), list ops over List<Code> (equality-keyed, case kept),
Coalesce/case/First over clinical values, ToConcept roundtrips, and
`.codes` aggregates. Gate 2832/2832. Tests: two new
`test_cql02_explorer_*` dual-backend tests in
fhir4ds/cql/duckdb/tests/integration/test_clinical_type_parity.py (now 24).

### CQL Temporal and Complex Conversion Boundaries
CQL Date, DateTime, Time, Quantity, and Ratio conversion functions must stay
spec-aware at the public DuckDB SQL surface. Do not rely on generic DuckDB
casts for temporal conversion because they can accept malformed offsets or erase
CQL precision/offset text. `ConvertsToDate*`/`ConvertsToTime` must validate
both lexical shape and calendar/time ranges. `ToQuantity` must return NULL, not
raise, for malformed numeric strings. `ToRatio` must support the CQL string
form `<quantity>:<quantity>` while accepting internal JSON-shaped ratios only
when numerator and denominator are valid Quantity objects with numeric values.
Keep native-loaded and forced Python fallback DuckDB parity tests together when
changing these helpers.

CQL-03 SKEPTIC fresh rerun tightened this boundary further: timezone offsets
past `+/-14:00`, including `+14:01`, must return false/NULL through
`ConvertsToDateTime`, `ToDateTime`, `ConvertsToTime`, `ToTime`, and translated
`convert` paths. JSON-shaped Quantity/Ratio internals require JSON-numeric
Decimal `value` fields, not numeric-looking strings, and Ratio value/unit
helpers must return NULL when numerator or denominator is not a valid Quantity.
Keep Python fallback, native-loaded C++ registration, direct native SQL tests,
and `test_temporal_complex_parity.py` aligned.

CQL Date/DateTime/Time constructors are public temporal boundaries, not string
formatting shortcuts. Runtime constructor output must be validated by the same
temporal parser path used by public helper UDFs so invalid dynamic values such
as `Date(year from @2024-01-01, 13)`, `DateTime(..., hour: 24)`, or timezone
offsets beyond `+/-14:00` return SQL NULL instead of leaking malformed lexical
values. `Time(hour, minute, second, millisecond)` preserves CQL time string
precision including the `T` marker and milliseconds. Time-only quantity
arithmetic is clock-domain arithmetic: preserve input precision and keep native
C++ and Python fallback behavior aligned across midnight.

CQL-03 HISTORIAN fresh rerun found that static DateTime constructor
`timezoneOffset` lowering must treat the offset as a Decimal-hours component,
not generic string formatting. Literal offsets near the boundary such as
`13.999` must round/carry to a valid ISO `+14:00` suffix instead of emitting
`+13:60`, and non-Decimal static offsets such as `true` or `'1'` must be
rejected rather than silently coerced or ignored. Keep this covered in
`test_temporal_complex_parity.py` and the CQL-03 fresh probe.

CQL-03 EXPLORER (2nd rerun, 2026-08-20, spec-compliance campaign) closed six
more temporal/complex gaps, all dual-backend: (1) the property-style temporal
component accessors (`X.month`, `X.year`, `X.hour`, `X.date`, `X.time`) are
the same operator as `month from X` (CQL 1.5 §09-b) and now route through
`dateComponent` via `_translate_temporal_component_property`
(_temporal_components.py, hooked early in `_translate_property`); gating uses
the standalone `_static_source_cql_type` helper because `_infer_cql_type`
lives on the library translator, not the ExpressionTranslator mixin stack;
(2) temporal-literal defines referenced by alias now inline at reference
sites (`_is_static_temporal_definition` in _query.py + choke point in
`_translate_identifier`) — the same patient-id-less-CTE Binder family CQL-02
fixed for clinical literals; (3) CQL 1.5.3 §1.6/§1.11: seconds and
milliseconds are ONE combined decimal precision for comparison ("When
milliseconds are null, they are combined as .0") — implemented in BOTH
`_compare_at_min_precision` (Python) and C++ `CompareTemporal`; the
interval-boundary helper `_precision_aware_compare` MUST pass
`combined_seconds_ms=False` because official fixture DateTimeIncludedInNull
pins interval-boundary second-vs-ms mismatch as uncertain (fixtures outrank
prose); extension rebuilt/deployed md5 10eaecdb10d3e8fca597078fc94c999e;
(4) Ratio `.numerator`/`.denominator` carry Quantity typing into arithmetic
dispatch (`_is_cql_quantity_expr` via `_static_source_cql_type`, ToRatio-aware)
so `.numerator + 5 'mg'` routes to quantity_add, not dateAddQuantity;
(5) `.timezoneOffset` parses as a property name (parser accepts TIMEZONE_FROM
as identifier; cql.g4 lists 'timezoneoffset' as keywordIdentifier) and lowers
to `cqlTimezoneOffset`; (6) `ToTime` returns T-prefixed Time strings (Python
supplement only; no C++ counterpart) — the T marker is load-bearing for
dateComponent extraction. NOT A BUG registry: E-notation numeric literals
(`1E3`, `9.9E25`), ToQuantity/ConvertsToQuantity/ToDecimal E-notation strings
are correctly rejected — official fhirpath.g4 `NUMBER: [0-9]+('.' [0-9]+)?`
has no exponent. Coverage: 4 new dual-backend tests in
test_temporal_complex_parity.py (now 24); stale uncertainty pins in
test_list_part2_parity.py updated with spec citations. Gate 2832/2832.

CQL-03 EXPLORER fresh rerun found that expression-valued Date/DateTime/Time
constructor components need the same type boundary as literals. Statically
known Boolean/String component expressions such as `Date(2024, 1 = 1, 1)`,
`Time(1 = 1, 0, 0)`, and `DateTime(..., 1 = 1)` must raise translation
errors; runtime expressions with non-Integer components or non-numeric
timezone offsets must return SQL NULL rather than relying on DuckDB Boolean or
String casts. Keep native-loaded and forced Python fallback execution parity
in `test_temporal_complex_parity.py`.

CQL `ToQuantity` has multiple public shapes: strings such as `5 'mg'`,
numeric Integer/Long/Decimal values that become unit `1`, and internal
JSON-shaped Ratio values that divide numerator by denominator. Native-loaded
connections must shadow the legacy C++ `ToQuantity(VARCHAR)` with the Python
conformance helper until the C++ surface implements the same overloads.
`ConvertsToQuantity` over JSON-shaped values must require a finite Decimal
`value`, not just the presence of a `value` key.

CQL-06 SKEPTIC fresh rerun fixed conversion macro registration visibility:
private helpers behind `ToDate`, `ToDateTime`, and `ToTime` may ignore duplicate
registration/catalog conflicts, but unexpected registration failures must raise
instead of leaving public macros pointed at missing helpers. Keep
`test_conversion_check_parity.py`, `.temp/qa/cql06_skeptic_probe.py`, and full
conformance aligned when changing conversion macro registration.

CQL-06 HISTORIAN fresh rerun tightened Quantity/Ratio conversion checks:
`ToQuantity` and `ConvertsToQuantity` must reject public Quantity strings whose
decimal value exceeds the implementation `DECIMAL(38, 8)` range/scale, and
`ConvertsToQuantity` must return true for valid Ratio JSON because
`ToQuantity(Ratio)` is supported. Keep the strict Decimal guard at public
conversion boundaries such as `ToQuantity`, `ConvertQuantity`,
`ConvertsToQuantity`, and `ConvertsToRatio`; do not move it into generic
`parse_quantity`, because translated measure arithmetic can produce
intermediate Quantity JSON with more than 8 fractional digits before comparison.
CMS832 is the DQM regression sentinel for that boundary.

CQL-06 SKEPTIC (2026-08-20, spec-compliance campaign) fixed the ToQuantity
string grammar for bare calendar duration keywords: CQL 1.5 Appendix B
§ToQuantity admits a unit designator that is "a valid, case-sensitive UCUM unit
of measure or calendar duration keyword, singular or plural", and Table 9-G's
round-trip rule (`ToString(4 days)` results in `4 days`) requires
`ToQuantity('4 days')` to parse. `toQuantity` in `udf/quantity.py` previously
accepted only the quoted form (`5 'mg'`), so `ConvertsToQuantity('5 years')`
and `ConvertsToRatio('5 years:2 days')` incorrectly returned false/null. The
bare token alternative is gated on `_CQL_CALENDAR_DURATION_UNITS`
(case-sensitive; 'Years' is rejected), and bare non-calendar UCUM tokens
('5 mg') stay rejected because UCUM units must appear as a quoted string
literal. Regression test:
`test_conversion_check_parity.py::test_cql_to_quantity_accepts_bare_calendar_duration_keywords_cql06_skeptic`.

CQL-06 EXPLORER fresh rerun tightened String conversion checks:
`ConvertsToString` and generic translated `ToString` must route through the
spec-aware macro boundary and reject structural List/Tuple/JSON values rather
than inheriting DuckDB `CAST(... AS VARCHAR)` behavior. Quantity and Ratio
remain special cases that use `QuantityToString` and `RatioToString`.
CQL-07 SKEPTIC fresh rerun extended this guard to statically known Interval and
clinical Concept values. These are often transported as `VARCHAR` JSON after
translation, but that transport shape is not String type evidence:
`ToString(Interval[...])`, `convert Interval[...] to String`,
`ToString(ToConcept(...))`, and `ConvertsToString(ToConcept(...))` must lower
to NULL/false rather than serializing implementation JSON.
CQL-07 HISTORIAN found the same scalar-alias boundary for conversion-check
predicates. Static definition aliases used as arguments to `ConvertsTo*`,
`CanConvertQuantity`, or `ConvertQuantity` must inline the original scalar AST
when it has no retrieve/query dependency; otherwise Quantity/Ratio aliases can
fall through to missing resource CTE lookups such as
`SELECT sub.resource FROM "QuantityFromString"`. Keep
`test_conversion_check_parity.py` and fresh CQL-07 probes covering static
Quantity/Ratio aliases for `ConvertsToString`, `ConvertsToQuantity`, and
`ConvertsToRatio`.
CQL-07 EXPLORER found the conversion-function version of the Quantity alias
boundary. Definitions produced by `ToQuantity(...)`, including through an
inlined user-defined function, must preserve `Quantity` CQL type metadata and
project scalar `value` columns so later `ToString(Q)` or `convert Q to String`
routes through `QuantityToString` instead of serializing internal Quantity
JSON. Keep `test_conversion_function_parity.py` population-SQL coverage and
`.temp/qa/cql07_explorer_probe.py` aligned when changing conversion return-type
inference or static definition inlining.

CQL current-clock and precision Date/Time helpers are public compatibility
surface. `TimeOfDay()` translation and `dateTimeTimeOfDay()` must return CQL
time strings with a leading `T`, so component extraction and
`same <precision> as` comparisons parse consistently. Direct `dateTimeSameAs`,
`dateTimeSameOrBefore`, and `dateTimeSameOrAfter` must use the same
timezone-normalizing, uncertainty-aware semantics as `cqlSameAsP`,
`cqlSameOrBeforeP`, and `cqlSameOrAfterP`; invalid precision strings such as
`week`/`bogus` return SQL NULL consistently in forced Python fallback,
native-loaded, and no-Python C++ surfaces. `Time(...)` constructor components
are Integer-valued, invalid ranges return NULL at execution, and native
date/time quantity subtraction must preserve parity for fractional day/week
date-only arithmetic. In particular, one-argument `Time(hour)` is a constructor
(`T12`), distinct from `time from <DateTime>` extraction, and fractional week
quantities truncate to an integer week count before Date subtraction in both
Python fallback and no-Python C++ surfaces.
DateTime values with timezone offsets are normalized only for hour-or-finer
precision comparisons; year/month/day precision compares local DateTime
components. Time-only values with offsets are not DateTime values and must not
be routed through DateTime timezone normalization, because midnight-adjacent
times can otherwise underflow and Python fallback can raise instead of
returning a row-resilient Boolean/NULL.
Translated numeric component extraction must route through `dateComponent`
rather than ad hoc string slicing. Timezone-suffixed values without millisecond
precision, such as `@2024-01-01T10:00:00+05:00`, return SQL NULL for
`millisecond from ...`; they must not slice the timezone offset and cast it.

Only apply the static clinical `as` shortcut when the source expression has a
known clinical type. Dynamic FHIR values such as `Observation.value as Concept`
must fall through to runtime matching; lowering unknown dynamic clinical values
to NULL can erase valid CodeableConcept comparisons in DQM SQL.

Clinical `~` must preserve full Code/Concept equivalence semantics. Code
equivalence compares code+system and ignores display/version; Concept
equivalence is a non-empty intersection of contained Codes. Do not flatten
Concept references to a single dict or route dynamic `CodeableConcept ~ Concept`
to a bare `coding.exists()` check without target code predicates. Static
clinical type inference must also flow through query `let`/`return` and
`singleton from` aliases so clinical `is`/`as` does not fall through to FHIR
`resourceType` probing for JSON-shaped CQL values.

CQL list equivalence must preserve those clinical semantics after list
transport. `List<Code>` and `List<Concept>` values produced by aliases,
`singleton from`, or direct helper calls must not compare raw JSON display or
version fields for `~`; route them through Code/Concept equivalence while
leaving list equality/display-sensitive set operations on CQL equality. Also
keep a Quantity list distinct from a scalar Quantity: `{ 1 'g' } = { 1000
'mg' }` uses CQL list equality with unit-aware element comparison, while
`singleton from { 1 'g' }` is the scalar Quantity case.
`IndexOf` uses the same element equality boundary: incompatible Quantity units
or clinical Code values whose equality is unknown return SQL NULL when no true
match exists, not `-1`. Query-produced list sources for translated `IndexOf`
must be folded into list values before calling `CQLIndexOf`.

CQL-19 SKEPTIC fresh rerun (2026-07-02) found one translation gap: the
symbolic form of the union operator (`|`) per CQL §20.29 ("the union operator
can also be invoked with the symbolic operator (|)") must route through the
same `_translate_union_op` dispatcher as the keyword `union` form. The CQL
parser emits `BinaryExpression(operator="|", ...)` for the symbolic form and
`BinaryExpression(operator="union", ...)` for the keyword form; the
translator's binary-expression dispatch must accept BOTH operator strings at
every dispatch site that handles union (currently three: the main
`_translate_union_op` dispatch in `_operators.py`, `_temporal_list_ast_kind`
type inference in `_operators.py`, and `_translate_first_last_with_window`'s
union-source detection in `_lists.py`). Audit pattern for similar symbolic-
form coverage gaps: `grep -rn "TokenType\." fhir4ds/cql/parser/parser.py`
finds every symbolic-token binary-expression emission, then
`grep -rn 'operator == "' fhir4ds/cql/translator/` confirms every emitted
operator string has a translator match. Future CQL symbolic operators added
to the parser MUST have a matching translator dispatch entry, or they will
fall through to SQL pass-through and produce BinderExceptions at execution.

CQL interval operators must preserve Quantity shape at interval boundaries.
Do not reduce Quantity bounds or points to bare numeric values before
comparison; `Interval[1 'g', 2 'g'] contains 1500 'mg'` depends on the same
unit-aware comparison surface as ordinary Quantity ordering. Incompatible
Quantity dimensions such as `Interval[1 'g', 2 'g'] contains 1 'cm'` must
return SQL NULL in Python fallback, native-loaded, and no-Python C++ DuckDB
surfaces, not Python comparison errors or `false`. Interval-valued set-operation
outputs such as `intervalExcept`, `intervalIntersect`, and `intervalUnion`
remain interval expressions for downstream `contains`, `includes`, equality,
and precision operators; translator dispatch must not fall through to generic
DuckDB list/string functions for nested interval composition.
Public `expand` and `expand_points` default the `per` step only when `per` is
omitted or SQL NULL. A supplied malformed Quantity JSON `per`, including
missing/non-numeric `value` or string/Boolean values, must return SQL NULL in
Python fallback, native-loaded, and no-Python C++ surfaces.
Typed null interval bounds are internal unbounded-bound markers, not public
Start/End values. For closed null bounds, `start of` and `end of` must return
the CQL minimum/maximum for the inferred point type, for example Integer
`-2147483648`/`2147483647`, Date `0001-01-01`/`9999-12-31`, and Time
`T00:00:00.000`/`T23:59:59.999`; open null bounds still return SQL NULL. Keep
translated CQL, direct public helper calls, forced Python fallback,
native-loaded registration, and no-Python/browser C++ aligned.

### DQM Population Attribution
`MeasureEvaluator.summary_report()` must apply subject-based proportion
population labels in FHIR CQM order, not by independently counting raw CQL
definition truth values. Label denominator only inside initial population,
denominator exclusion only inside denominator, numerator only after denominator
exclusion is removed, denominator exception only for denominator/non-excluded
patients that did **not** meet numerator, and numerator exclusion only inside
numerator. Aggregate caps cannot repair patient-level misattribution: if the
only numerator patient is denominator-excluded, numerator_final is 0; if a
denominator-exception patient also meets numerator, the exception does not
remove that patient from denominator_final.

**Release 0.0.7 Domain 4 confirmation (2026-05-24).** The current
`summary_report()` population mask order matches these FHIR CQM attribution
rules across synthetic edge cases: denominator exclusions are removed before
numerator counting, denominator exceptions apply only to denominator/non-
excluded patients that did not meet numerator, and numerator exclusions apply
inside numerator only. Keep `test_evaluator.py` population-order tests, DQM
integration tests, and DQM conformance together when changing this logic.

**Release 0.0.7 Domain 9 fix (2026-05-24).** DQM audit evidence and narratives
must use the same effective population masks as summary attribution for
exclusion-style populations. Preserve the raw CQL definition `result`, but add
and narrate from `effective_result` for denominator exclusions, denominator
exceptions, and numerator exclusions when the required gating populations are
present. This prevents denominator exceptions from being narrated as applied
for numerator-positive patients and numerator exclusions from being narrated as
applied outside the numerator.

### ViewDefinition Canonical Constants
Built-in FHIRPath variables (`%context`, `%resource`, `%rootResource`, `%ucum`, `%rowIndex`)
are canonically defined in `fhir4ds/viewdef/constants.py:FHIRPATH_BUILTIN_VARIABLES`.
The generator imports from this canonical source. Do not duplicate this set.

See `docs/architecture/CQL_TRANSLATOR_AUDIT_2026Q2.md` for the detailed issue log.

### C++ Extension Security
All JSON injection sites have been remediated with `escapeJsonString()`.
- `evaluator.cpp:711` type() — **fixed** (uses escapeJsonString)
- `interval.cpp` to_json() string bounds — **fixed** (Pass 4)
- `interval.cpp` width_string() — already safe (numeric output only)
- `quantity.cpp` wrapInConcept — **null deref fixed** (Pass 4)
Regex hardening was tightened in review-10 remediation (2026-05-17):
native `matches()`/`replaceMatches()` now reject overlong patterns and common
catastrophic backtracking shapes before compiling `std::regex`; direct Python
string helpers apply the same nested-quantifier/alternation guard. RE2 migration
remains the stronger long-term option for fully untrusted regex input, but new
regex paths must at minimum call the shared guard before evaluation.

### C++ Fast Path: FHIRPath Resource-Type Prefix Rule

**Fixed in 2026-Q2 (commit fb920e1e).** This section documents the pattern to prevent future regressions.

FHIRPath expressions may begin with a resource type qualifier that is semantically transparent:
`Observation.valueQuantity.value` is identical to `valueQuantity.value` when evaluated against an Observation resource. The first segment is **not a JSON key** — it is a type filter.

The Phase 7 fast path in `fhirpath_extension.cpp` must honor this rule. The helper `ComputeSegStart(yyjson_val *root, segments)` reads the `resourceType` field from the already-parsed root object and returns `1` if `segments[0]` matches it, otherwise `0`. Both `FastPathLookup` and `FhirpathNumberFunction`'s inline fast path call this before walking the segment list.

**Three invariants to maintain in `fhirpath_extension.cpp`:**

1. **`ComputeSegStart` always uses the already-parsed root** — never call `yyjson_read` a second time just to compute the prefix skip. The JSON is parsed once; `ComputeSegStart` gets a `yyjson_val*`.

2. **Fast-path misses must fall through to `EvaluateFhirpath`** — if the fast path finds the node but it is not the expected type (e.g. `fhirpath_number` finds a string value), fall through instead of emitting NULL. `fhirpath_text` already does this; `fhirpath_number` was fixed to match.

3. **Guard `seg_start >= segments.size()`** — if the prefix skip consumes all segments (e.g. expression `'Patient'` with no field path), `FastPathLookup` returns `{false,""}` and the caller falls through to the full evaluator rather than serialising the entire root object.

When adding a new `fhirpath_*` UDF function with a fast path, copy this pattern from `FhirpathNumberFunction`. Any new fast path that omits these three invariants will silently return NULL for all resource-type-prefixed expressions.

### C++ Extension: Type Coercion Bugs in toNumber() and FastPathLookup

**Discovered in QA Iteration 5 (ARCHAEOLOGIST).** Three bugs cause behavioral divergence between the C++ extension and the Python fallback:

1. **`fhirpath_number` converts strings to numbers** (CRITICAL) — `toNumber()` in `evaluator.cpp:3439-3444` calls `std::stod()` on string values and returns `0.0` on failure instead of signaling that the conversion failed. The caller (`FhirpathNumberFunction`) should return NULL for non-numeric types. **Fix**: `toNumber()` should return a sentinel (e.g., NaN with a flag) or the caller should check the effective type before calling `toNumber()`.

2. **`fhirpath_number` converts booleans to numbers** (CRITICAL) — `toNumber()` in `evaluator.cpp:3437-3438` converts `true` → `1.0` and `false` → `0.0`. FHIRPath booleans are not numbers. **Fix**: Remove the boolean case from `toNumber()` or add type-checking in `FhirpathNumberFunction`.

3. **`fhirpath_text` fast path returns string "null" for JSON null** (HIGH) — `FastPathLookup` in `fhirpath_extension.cpp:278-284` serializes JSON null via `yyjson_val_write()` as the string `"null"` without checking `yyjson_is_null()`. **Fix**: Add `if (yyjson_is_null(current)) { yyjson_doc_free(doc); return {false, ""}; }` before the serialization fallback.

**Pattern**: All three bugs share the same root cause — the C++ path doesn't validate type constraints before producing output, while the Python fallback uses `isinstance()` checks that naturally reject non-numeric types.

### C++ Extension: fhirpath_date and fhirpath_json Null Handling

**Discovered in QA Iteration 6 (SKEPTIC).** Two bugs cause behavioral divergence between the C++ extension and the Python fallback:

4. **`fhirpath_date` passes non-date strings through** (MEDIUM) — `FhirpathDateFunction` in `fhirpath_extension.cpp` called `toString()` on the first result and returned it as-is without validating date format. `fhirpath_date({"v":"hello"}, 'v')` returned `"hello"` instead of NULL. **Fix**: Added date format validation checking YYYY (4 digits), YYYY-MM (7 chars), YYYY-MM-DD (10+ chars) patterns.

5. **`fhirpath_json` returns "[]" for empty results** (MEDIUM) — `FhirpathJsonFunction` always built a JSON array string, even for empty collections. `fhirpath_json({"v":null}, 'v')` returned `"[]"` instead of SQL NULL. **Fix**: Added `fp_results.empty()` check returning NULL before array building.

**Pattern**: Same root cause as bugs 1-3 — the C++ path doesn't validate output constraints that the Python fallback naturally enforces through `isinstance()` checks and list length validation.

### C++ Extension: fhirpath_json Serialization and fhirpath_bool String Validation

**Discovered in QA Iteration 7 (HISTORIAN).** Two bugs cause behavioral divergence between the C++ extension and the Python fallback:

6. **`fhirpath_json` double-encodes non-string values as strings** (HIGH) — `FhirpathJsonFunction` called `toString()` on every result and wrapped it in quotes. Objects produced `["{\"given\":[\"John\"]}"]` instead of `[{"given":["John"]}]`. Booleans produced `["true"]` instead of `[true]`. **Fix**: Type-aware serialization — Integer/Decimal/Boolean output as native JSON types, JsonVal uses `yyjson_val_write()`, Quantity serializes as `{"value":X,"unit":"Y"}`, String values starting with `{`/`[` output as raw JSON.

7. **`fhirpath_bool` accepts non-"true"/"false" strings** (MEDIUM) — The C++ evaluator's `toBoolean()` converted any non-empty string to true (e.g., `"yes"` → `true`). The Python fallback rejects non-"true"/"false" strings. **Fix**: Added string validation in `FhirpathBoolFunction` that checks String and JsonVal types for exactly "true" or "false" (case-insensitive) before calling `toBoolean()`.

### C++ Extension: Use-After-Free in FhirpathNumberFunction Fast Path

**Discovered in QA Iteration 10 (ARCHAEOLOGIST).** A genuine memory safety bug (not a behavioral divergence):

8. **`fhirpath_number` fast path has Use-After-Free** (CRITICAL) — `FhirpathNumberFunction` in `fhirpath_extension.cpp:517-556` called `yyjson_doc_free(doc)` and then dereferenced `current` (a `yyjson_val*` pointing into the freed document) to check types and extract values. Undefined behavior that could silently corrupt data under memory pressure. **Fix**: Extract `yyjson_is_int()`, `yyjson_is_real()`, `yyjson_get_sint()`, `yyjson_get_real()` into local stack variables (`is_int`, `is_real`, `extracted`) **before** calling `yyjson_doc_free`. This matches the pattern used by `FastPathLookup` which materializes values into owned strings before freeing.

**Pattern**: This is the first memory safety bug found in the QA loop. Unlike all previous bugs (behavioral divergences found by comparing C++ vs Python output), this class of bug requires manual code archaeology of pointer lifecycles. The code "worked" because the allocator typically hadn't reused the freed memory yet, but could produce garbage under memory pressure or with alternative allocators.

### FHIRPath Collection Equality and DuckDB Wrapper Resilience

**Discovered in the fresh 0.0.5 release loop rerun (2026-05-15).** Multi-item equality must use ordered collection semantics, not singleton-only empty propagation. The official R4 conformance case `(1 | 1) = (1 | 2 | {})` expects `false`; same-length collections compare element-by-element. The C++ evaluator in `extensions/fhirpath/src/fhirpath/evaluator.cpp` was fixed to return boolean results for multi-item `=`/`!=` instead of empty.

The Python core evaluator must remain spec-strict for execution errors such as multi-item `as(...)`, but DuckDB-facing wrapper UDFs should preserve row-level resilience by converting `FHIRPathError` to empty/NULL outside strict mode. This keeps direct conformance behavior and SQL UDF behavior intentionally distinct.

### CQL Boundary Helper String Classification

**Discovered in CQL-10 HISTORIAN (2026-Q2).** `HighBoundary` and `LowBoundary` public helper surfaces have broader string input needs than static CQL literal syntax:
- Numeric text such as `'1.587'` must be treated as decimal boundary input in Python fallback and native C++ surfaces.
- Four-digit year-only text such as `'2014'` must remain year-precision date input for official CQL boundary semantics.
- Time-only strings may carry `Z` or `+/-HH:MM` suffixes in public helper and conversion surfaces; preserve the suffix after filling missing components.

Do not broaden static CQL time literal parsing to accept `@T...Z` or `@T...+/-HH:MM`. The official CQL XML treats offset-bearing time literals as invalid grammar in that path, even though `ToTime('T14:30:00.0Z')` and direct DuckDB helper strings can handle them.

### CQL Arithmetic Public Surface Parity

**Discovered in CQL-10 EXPLORER (2026-Q2).** Public CQL DuckDB helper UDFs are part of the compatibility surface, including C++-only/browser direct calls. Keep `HighBoundary`/`LowBoundary` aligned across native C++ and Python fallback for exponent numeric text, invalid temporal strings, and DateTime timezone suffixes. Native date quantity helpers must reject invalid Date/DateTime strings and invalid or empty Quantity JSON, and preserve fractional day/week arithmetic for hour-or-finer DateTime inputs.

Quantity/scalar arithmetic must return SQL NULL when the scalar or Quantity value is NULL, or when dividing by zero. Do not emit Quantity JSON with a null `value`. One-argument `Log` should lower through `mathLn`, and Date/DateTime +/- Integer should lower through date quantity helper calls rather than binder-sensitive SQL interval literals.

Translated numeric `HighBoundary`/`LowBoundary` must cast the public helper result through `VARCHAR` before the final numeric `TRY_CAST`. The Python default-precision helper macro can transport a DuckDB `UNION(VARCHAR, DOUBLE)`, and direct `TRY_CAST(HighBoundary(decimal) AS DOUBLE)` returns NULL even though the direct helper fetch displays a numeric boundary value.

**Hardened in milestone review-30 (2026-Q2).** Boundary helper and temporal helper validation applies to direct public UDF calls, not only translated CQL. Reject malformed Date/DateTime bodies, non-finite numeric text, impossible offsets, colonless offsets, and unbounded exponent expansion. `Now()` must normalize DuckDB `CURRENT_TIMESTAMP` offsets from `-HH` to `-HH:00` before strict timezone parsing. Native `quantityToInterval` and date quantity helpers return NULL for invalid/empty/huge Quantity input, and date quantity arithmetic preserves date-only precision. Native `ToQuantity` numeric and Boolean overloads are required for C++-only/browser parity. Quantity/scalar `*` and `/` over FHIR `value[x]` must use `fhirpath_number`/`TRY_CAST`, not plain `CAST`; `Power()` and `^` route through `mathPower` with an outer numeric `TRY_CAST`.

**Hardened in CQL-11 SKEPTIC/HISTORIAN (2026-Q2).** Arithmetic Part 2 public helpers must be parity-tested across native-loaded DuckDB registration, forced Python fallback registration, and C++-only/browser-style surfaces where functions/macros are registered. Current CQL Reference `Round` examples require negative half ties to round away from zero (`Round(-0.5) = -1`), and null precision is defined as precision `0`; keep SQL macros, Python fallback `mathRound`, native C++ `mathRound`, and the local arithmetic conformance XML aligned to that normative text. `Power` and direct `mathPower` return NULL for NaN, infinity, or unrepresentable results. Quantity `mod` and truncated `div` with compatible units convert the right operand into the left operand unit before arithmetic and preserve the left operand unit. Direct `predecessorOf`/`successorOf` helpers return NULL at public SQL boundaries for row resilience, while translated static temporal underflow/overflow remains an invalid CQL expression for official conformance. Maximum/minimum `DateTime` and `Time` literals retain the CQL `T` marker and millisecond precision. Fresh CQL-11 SKEPTIC rerun also fixed Quantity predecessor/successor shape: integer-authored Quantity values step by 1, decimal-authored Quantity values step by `1e-8`, and numeric-string Quantity JSON returns SQL NULL across Python fallback, native-loaded, and no-Python C++ surfaces.

**Hardened in CQL-11 HISTORIAN (2026-Q2).** Arithmetic Part 2 dynamic FHIR `value[x]` operands must use typed numeric projection (`fhirpath_number`) for numeric-only operations such as `div`, `Power`/`^`, `Round`, and `Truncate`; `fhirpath_text` plus SQL coercion can both binder-fail and incorrectly accept `valueString`. Apply CQL representational boundary rules in translation for static min/max cases: `-(minimum Integer)` and `-(minimum Long)` are NULL, `-(minimum Decimal)` is the positive maximum Decimal, and Decimal predecessor/successor at min/max is NULL. Static DateTime literal boundary underflow/overflow is invalid just like constructor boundary cases. Public helper parity also covers invalid time strings, unrepresentable `mathPower`, and DateTime precision with `+/-HH:MM` timezone suffixes, whose digits do not count as precision.

**Hardened in CQL-11 EXPLORER (2026-Q2).** CQL Arithmetic Part 2 direct SQL macros are public compatibility surface: `Div(x, y)` must truncate toward zero for Decimal operands and return NULL on zero divisor. `minimum DateTime` and `maximum DateTime` use the official XML UTC boundary suffix `Z`. Predecessor/successor over Date, DateTime, and Time values is precision-aware and preserves lexical precision (`YYYY`, `YYYY-MM`, `YYYYT`, `YYYY-MMT`, `YYYY-MM-DDTHH`, `T12`, `T12:30`, etc.). DateTime marker forms are DateTime values, not numeric text. Mixed scalar/Quantity `mod` and `div` must convert scalar operands to unit `1` Quantity JSON before UDF dispatch; never emit `parse_quantity(<number>)`.

**CQL-11 EXPLORER follow-up (2026-Q2).** `maximum Quantity` and
`minimum Quantity` return exact DECIMAL-backed Quantity JSON with unit/code
`1`; unsupported maximum/minimum types raise translation errors rather than SQL
NULL. Query-source literal lists and single-Quantity `singleton from` lists must
preserve raw Quantity JSON spelling so integer-authored Quantity
predecessor/successor semantics survive aliases and singleton extraction.
Public C++-only `predecessorOf/successorOf(VARCHAR)` treats numeric text as
Decimal; typed Integer/Long still use the BIGINT overloads.

**Hardened in CQL-11 EXPLORER 2nd rerun (2026-08-21).** The Integer-range
successor/predecessor boundary rule is NOT limited to literal operands:
`successor of Coalesce({2147483647})` and any statically Integer-typed
non-literal operand must translate to a `CASE WHEN operand >= maximum Integer
THEN NULL ELSE successorOf(...) END` guard (predecessor mirrored at the
minimum), because the shared BIGINT helper clamps only at Long bounds and
DuckDB/Python UDFs cannot register an Integer-specific overload
(`create_function` rejects duplicate names). Static inference flows through
`_infer_static_numeric_type`, which now understands `Coalesce(...)` of
numeric literals/lists; mixed-type or unknown operands keep the plain helper.
Unary negation of `days/months/... between` and `difference in ... between`
results is valid CQL (Integer-valued) and lowers to
`- TRY_CAST(cqlDurationBetween/cqlDifferenceBetween(...) AS BIGINT)` — the
VARCHAR-returning helpers must never meet a bare prefix minus. Python
`quantityNegate` must flip the value and re-serialize preserving the unit
verbatim (native JSON key order value/unit/code/system); pint round-trips
normalize calendar-duration keywords ('day' → 'd') and diverge from native.
`parse_expression` raises `ParseError` on trailing tokens; bare Time literals
without the `@` prefix are malformed, not silently truncated.

**Hardened in CQL-13 SKEPTIC (2026-Q2).** Date/time `duration between` with
uncertain operands must cap the high end at the requested precision, unlike
`difference between` which counts crossed boundaries. The current CQL Reference
example `months between @2012-01-02 and @2012` is `Interval[0, 10]`; the
corresponding month `difference` remains `Interval[0, 11]`. Keep Python
fallback, native-loaded registration, and no-Python/browser-style C++ helper
tests together for `cqlDurationBetween` / `cqlDifferenceBetween`.

**Hardened in CQL-13 EXPLORER (2026-Q3).** Calendar `duration between` at
year/month targets requires DAY precision on BOTH operands for a certain
result — a month-precision operand (partial FHIR birthDate `1975-03`) must
yield the uncertainty interval, mirroring the official
`years between DateTime(2005) and DateTime(2010) // Interval[4,5]`; the
prior `s_idx > unit_idx` rule wrongly made month-precision "certain" for
year targets (crisp 45 where the true range was [44,45]). Date-only
operands use the MIDNIGHT convention in duration uncertainty boundaries:
the start high boundary must not carry a phantom 23:59:59.999 that flips
exact anniversary boundaries (Jun 1 2012 + 19mo = Jan 1 2014 was returned
as 18). Python `_duration_in_calendar_years/_months` strip tzinfo
(`_wall_clock`) so mixed naive/aware operands no longer null out — C++
compares wall components; keep both engines lockstep. Constructors
(translator `_temporal_components.py`): trailing static-null components are
the sanctioned partial form EVEN below a specified timezoneOffset
(`DateTime(2024,1,1,10,30,null,null,-7.0)` → `2024-01-01T10:30-07:00`), a
static-null timezoneOffset counts as unspecified, `Date(2024, null)` →
`2024`, but a static null ABOVE a specified component is the §22.5
DateInvalid form and raises at translation time; `DateTime(null)`
(all-null) still evaluates to null per the official fixture. Follow-up for
the age chunk: CalculateAge* UDFs still return crisp values for partial
birthDates (documented day-1 convention) rather than intervals.

**Hardened in CQL-14 EXPLORER (2026-Q2).** Date/DateTime/Time public quantity arithmetic helpers are row-resilient at malformed Quantity boundaries. Python fallback `dateAddQuantity` and `dateSubtractQuantity` must match no-Python/browser-style C++ behavior by returning SQL NULL for malformed JSON, missing `value`, null `value`, string or Boolean `value`, non-finite values, unsupported units, and huge values. Do not treat missing `value` as zero or coerce numeric strings. Valid arithmetic overflow remains an official invalid-expression error path for translated CQL conformance.

**Verified in CQL-14 SKEPTIC (2026-Q2).** Current-clock and precision Date/Time operators need cross-runtime coverage even when no remediation is required. Keep translated `Now() = Now()`, `Today() = Today()`, `TimeOfDay() = TimeOfDay()`, time-only `same` comparisons, invalid `week` precision NULLs, timezone-normalized same-second checks, null-gap Time constructor behavior, and partial DateTime month subtraction aligned across forced Python, native-loaded, and no-Python/browser-style C++ surfaces.

### CQL Interval Operator Boundaries

**Hardened in CQL-16 EXPLORER campaign launch (2026-08-22).** Two
native-only dual-engine bugs: (1) `BoundValue::compare` in
extensions/cql/src/cql/interval.cpp returned incomparable (-2) for
Integer-vs-Decimal interval bounds, so the no-Python native path returned
SQL NULL for meets/on-or-before/on-or-after/intersect and WRONG
deterministic FALSE for overlaps/included-in/overlaps-before-after/
equivalence (e.g. `Interval[1,3] overlaps Interval[2.5,5]` false; native
md5 87e4f6e8). CQL 1.5 §2 implicit conversions make numeric point types
cross-comparable — numeric compare (long double) precedes the type gate.
(2) Native `Interval::intersect` used raw bounds and propagated open flags;
§9.9 via §9.14/§9.15 Start/End requires effective bounds and an
always-closed result (reference IntersectEvaluator:
`new Interval(max, true, min, true)`): `Interval[1,5) intersect
Interval[4,8]` is `[4,4]`, not `[4,5)`. The Python authority normalized at
parse time; the native mirror now normalizes via successor/predecessor
before min/max. NOT A BUG registry: reference overlaps before/after is
start-based strict (`before(start1,start2) and overlaps`), so
`Interval[1,9] overlaps after Interval[1,5]` is false; hour-precision
DateTime successors step by hour. Coverage:
test_interval_part2_parity.py::test_cql_interval_part2_native_effective_bounds_and_cross_numeric_parity.

**Hardened in CQL-16 SKEPTIC campaign launch (2026-08-22).** Interval
Part 2 null-bound sentinels: a CLOSED null interval bound resolves to the
min/max of the point type (CQL 1.5 §9.14 Start / §9.15 End; reference
Interval.start/.end getters), so `meets` / `on or after` / `on or before`
return determined false/true rather than null (e.g. `Interval[1, null] meets
Interval[6, 10]` is false; `Interval[null, 5] on or after Interval[1, 3]` is
false). OPEN null bounds remain unknown (null). Successor/predecessor of the
maximum temporal sentinel overflows to null (Appendix C), which makes the
meets direction false; Python `_successor_for_bound`/`_predecessor_for_bound`
must keep catching OverflowError (a raw +1ms on 9999-12-31T23:59:59.999
raises) and native `meets_before_nullable` must return false (not NullOpt) on
successor overflow. Intersect result bounds follow the reference
IntersectEvaluator (max of effective starts, min of effective ends, always
closed) — `Interval[1,5] intersect Interval[null,3]` is `[1,3]`, NOT the min
sentinel. The `in` keyword accepts interval-valued left operands
(interval-interval Included In overload, reference InEvaluator routes through
includedIn); `_translate_in_op` must dispatch those to
intervalIncludedIn[Precise] before the point-in-interval BETWEEN lowering.
NOT A BUG (registry): integer-authored Quantity meets (`Interval[1 'g',3 'g']
meets Interval[4 'g',6 'g']`) is false — the live reference engine steps
Quantity successors by the Decimal 1e-8 rule (SuccessorEvaluator.kt converts
to Decimal), official fixtures pin only decimal-authored quantity meets, and
runtime Quantity JSON always serializes value as float by the documented
native-parity doctrine, so authored integer-ness is unrecoverable at runtime.
This supersedes the 2026-07-02 out-of-scope followup expectation of true.

**Hardened in CQL-15 SKEPTIC (2026-Q2).** Public `intervalStart` and
`intervalEnd` helpers expose CQL effective interval boundaries, not raw JSON
low/high fields. Open low bounds return the successor of the low value; open
high bounds return the predecessor of the high value. Date and day-precision
DateTime marker values step by one day, while timestamp-precision DateTime
values step by one millisecond; preserve marker formatting such as
`2024-01-30T`. Translator fallback extraction from `intervalStart(...)` and
`intervalEnd(...)` must treat those helper outputs as closed semantic bounds.
Do not reapply half-open flags after helper extraction or CMS/DQM expressions
such as `ends during day of Interval[..., ...)` can be double-excluded.
Keep forced Python fallback, native-loaded registration, and
no-Python/browser-style C++ direct helper parity tests together for these
public surfaces.

**Hardened in CQL-15 HISTORIAN (2026-Q2).** Interval equality and equivalence
must compare CQL semantic `Start`/`End` boundaries, not raw interval JSON shape
or authored open/closed flags. For example, `Interval(1, 6]` is equal and
equivalent to `Interval[2, 6]` because both have the same effective boundaries.
Translated `=`, `!=`, `~`, and `!~` over interval-valued operands must route
through interval-aware helpers rather than generic SQL JSON/text comparison.
Precision-aware interval public helpers such as `intervalBeforePrecise`,
`intervalIncludesPrecise`, and `intervalContainsPrecise` return SQL NULL when
partial Date/DateTime precision makes the relationship unknown. `Starts`/`Ends`
same-boundary helpers also return NULL when the required boundary is missing.
Keep forced Python fallback, native-loaded registration, and no-Python/browser
C++ direct helper coverage aligned for these paths.

**Hardened in CQL-16 SKEPTIC (2026-Q2).** Interval set/relationship helpers
must continue to use effective boundaries after open-endpoint normalization.
`Interval[1, 5) intersect Interval[5, 7]` is empty/NULL, not the point
interval `[5, 5]`. `overlaps before` and `overlaps after` are built on the
underlying `overlaps` relation; if temporal precision uncertainty or
incompatible Quantity dimensions make `overlaps` SQL NULL, the directional
overlap helper must propagate NULL rather than returning false. Keep direct
helper, translated CQL, forced Python fallback, native-loaded, and no-Python
C++ parity tests together.

**Hardened in CQL-16 EXPLORER (2026-Q2).** Translated precision-qualified
`overlaps`, `overlaps before`, and `overlaps after` over dynamic FHIR choice
values must preserve precision uncertainty without replacing the optimized
temporal decomposition that DQM relies on. Runtime values such as
`Observation.effective` can be concrete Periods or scalar Date/DateTime strings;
when decomposed bounds have fewer digits than the requested precision, the
translated predicate returns SQL NULL before doing lexicographic ISO-date
comparison. Partial temporal points such as `effectiveDateTime: "2014"`
compared at day precision return SQL NULL, not false, while concrete Period
values still evaluate normally across forced Python fallback, native-loaded
registration, no-Python C++, and DQM. Guard finite paired endpoints using the
raw `SQLInterval` / `intervalFromBounds` low/high expressions when available so
active unbounded intervals with a null high endpoint do not become unknown only
because their start has partial precision.

**Hardened in CQL-16 SKEPTIC iter 1 fresh run (2026-07-02).** Interval algebra
functions (`intervalIntersect`, `intervalExcept`) must route bound comparisons
through `_compare_interval_values` (Python) — NOT through `_normalize_for_compare`
followed by direct Python `<` / `>`. `_normalize_for_compare` deliberately
returns the original dicts when pint raises `DimensionalityError` for
incompatible Quantity dimensions (e.g. `Interval[1 'g', 3 'g'] intersect
Interval[1 'cm', 2 'cm']`); direct `<` / `>` then crashes with `TypeError`.
Sibling `intervalOverlaps` and `intervalUnion` were already immune via
`_precision_aware_compare`'s dict guard (line 1121-1122); the bug was isolated
to `intervalIntersect` and `intervalExcept`. C++ mirror: `Interval::except_of`
must explicitly check `BoundValue::compare` for -2 (incomparable) BEFORE
calling `Interval::overlaps`, because `overlaps` returns `false` on uncertainty
and `except_of` otherwise falls into the "no overlap → return a" branch,
returning interval1 unchanged instead of NULL. The C++ `Interval::intersect`
was already correct (returns NullOpt on compare -2 at line 1276). When fixing
any interval algebra comparison-safety bug, audit ALL sibling functions in the
family. Coverage: `test_cql_interval_part2_set_ops_incompatible_quantity_dimensions_null_cql16_skeptic`
(4 cases × 3 backends: Python fallback, native C++ with shadowing, no-Python
C++). Keep forced Python fallback, native-loaded registration, no-Python C++,
and full conformance parity-tested together.

**Out-of-scope followup from CQL-16 SKEPTIC (2026-07-02).** `intervalMeets` on
Quantity intervals currently returns False instead of the spec-required True
for `Interval[1 'g', 3 'g'] meets Interval[4 'g', 6 'g']` (end1=3, succ(3)=4,
start2=4 → meets). Root cause: `_successor_for_bound` returns None for Quantity
bounds. Per CQL §Predecessor/Successor: "For Quantity values, the successor is
equivalent to adding 1 if the quantity is an integer, and the minimum precision
value for the Decimal type if the quantity is a decimal." This is a pre-existing
gap not in CQL-16 chunk scope; flagged for future Quantity-successor work.

**CQL-17 EXPLORER (3rd launch) doctrine (2026-08-22):** interval-derived
scalars feeding arithmetic follow the interval's point type. `(start of
Interval[1, 5]) + 1` must lower to numeric DECIMAL arithmetic (CQL §19.19
Start returns the point type; §9 Add), never to the Date+Integer year-unit
path (`_is_cql_date_expression` matches ANY `start of`/`end of` unary) and
never to raw SQL `'+'(VARCHAR, x)` (binder error). Gate lives in
`_operators.py` +,-,*,/ dispatch via
`TemporalComparisonMixin._interval_scalar_point_kind` (covers `start of` /
`end of` / `point from` / `width of` unary ops and `Size`), which reuses the
HISTORIAN `_numeric_interval_point_kind` classifier; Quantity-kind scalars
route to quantity_add/subtract/multiply/divide with
`_quantity_operand_for_arithmetic`. Temporal interval scalars keep the
temporal paths. NOT A BUG registry: (1) width/size of Integer intervals
compute EXACT values even beyond the int32 point range (width of
Interval[-2147483648, 2147483647] = 4294967295) — pinned by the Long
MIN..MAX exact-value doctrine; do not "fix" to overflow-null without
superseding that doctrine. (2) interval `same day as` with an uncertain
start (null) and a known-different end (false) resolves to false via
three-valued AND, not null. (3) `same or before` (interval) compares END of
left vs START of right. (4) Size(Interval[1 'g', 3 'g']) = 2.00000001 —
Quantity point-size is the Decimal 1e-8 step. (5) Time interval bounds
serialize with the 'T' prefix in interval JSON. (6) point-from non-unit →
null is the documented DuckDB-UDF boundary (spec prose says run-time error;
flagged for human, unchanged).

**CQL-16 HISTORIAN doctrine (2026-08-22):** closed-null-bound sentinels must
follow the point type inferred from the peer bound, matching the reference
engine (Interval.kt start/end getters, Constants): Long peers (magnitude
beyond int32 — authored `L`-ness is erased at translation, so int32-range
Long peers keep Integer sentinels; documented boundary, unpinned by
fixtures) sentinel at int64 min/max; Quantity peers sentinel to
Quantity(MIN_DECIMAL/MAX_DECIMAL, unit) — implemented in
`_cql_minimum/maximum_for_peer_bound` (udf/interval.py) plus BOTH native
sentinel tables (`interval.cpp` sentinel_start/end_bound AND
`cql_extension.cpp` Minimum/MaximumForIntervalPointType used by
intervalStart/intervalEnd — keep them in lockstep). `_successor`/
`_predecessor` carry int64 Appendix C overflow guards, and Python
`intervalMeetsBefore` returns False (not None) on successor overflow,
matching native `meets_before_nullable`'s reference isMax guard. NOT A BUG:
`Interval[null, null] overlaps ...` → null (point type uninferrable →
Interval<Any> → reference minValue(Any) is null); `meets before day` /
`meets after <prec>` grammar spellings are not in the CQL 1.5 grammar
(ParseError is correct — precision qualifies `meets` only as `meets <prec>`);
Decimal successor step is 1e-8 so `Interval[null,1.5] meets Interval[1.6,5]`
is false.

**Fixed in Release 0.0.7 Domain 3 (2026-05-24).** Optimized translated
temporal `overlaps` SQL must preserve unbounded low-bound semantics. When
decomposing interval overlap to direct comparisons, coalesce null low bounds
to the minimum temporal sentinel (`0001-01-01`) just as null high bounds are
coalesced to the maximum sentinel (`9999-12-31`). Without this, expressions
such as `Interval[null, @2024-06-01] overlaps
Interval[@2024-01-01, @2024-12-31]` evaluate to SQL NULL instead of true.
Keep this covered by translated execution tests and public `intervalOverlaps`
native-loaded versus forced Python fallback parity checks.

### CQL String Operator Boundaries

**Hardened in CQL-12 SKEPTIC (2026-Q2).** CQL string operators need explicit null/boundary handling across translated SQL, Python fallback registration, native-loaded DuckDB registration, and no-Python/browser-style macro surfaces. `Combine` and `CombineSep` return NULL when the non-null filtered list is empty. `Substring` returns NULL for null/negative/at-or-past-end starts and null/negative lengths; do not inherit DuckDB's empty-string slicing for invalid CQL boundaries. `StartsWith` and `EndsWith` are exact prefix/suffix checks, so translated CQL must call the public macros rather than `LIKE`; `%` and `_` are data, not wildcards. String bracket indexing routes through the public `Indexer` macro instead of list extraction so at-end/out-of-range string indexers return NULL. Deprecated Python string UDFs should return NULL for null search operands or invalid substring inputs instead of raising.

**Hardened in CQL-12 HISTORIAN (2026-Q2).** CQL regex-backed string operators use single-line mode: unescaped `.` matches newline, and `^`/`$` provide whole-string anchoring when needed. DuckDB `Matches` and `SplitOnMatches` macros must pass regex option `s`, and `ReplaceMatches` must use `gs` for global single-line replacement while preserving CQL `$1` capture references and escaped literal dollars. Deprecated `stringMatches` should use `re.DOTALL` and return NULL for null patterns; deprecated string UDFs should keep row-level NULL resilience for null operands.

**Hardened in CQL-12 HISTORIAN re-launch (2026-08-21).** `Combine` whose source
lowers to a scalar `fhirpath_*` extraction (chained property-list navigation such
as `First([Patient]).name.given` — scalar navigation returns only the FIRST value
of a multi-valued element) must fail at translate time with a typed
`TranslationError`, never emit SQL that later crashes with an opaque DuckDB
`BinderException` (the `CombineSep` macro's `list_filter` lambda binds against the
scalar before the macro's type-guard `error()` can fire). Guard lives in the
Combine lowering step of `expressions/_functions.py`; supported sources (literal
lists, typed-null lists, folded query subqueries, `list_apply` row shapes) are
unaffected. Root dependency remains the deferred modelinfo chained-typing debt
(ARCH-001). Also verified conformant this launch: Unicode (codepoint-counted
`Length`/`Indexer`/`Substring`/`PositionOf`/`LastPositionOf`, ICU-less
`Upper('naïve')='NAÏVE'`), regex anchors/alternation/quantifiers/empty-match
replace/split, and `Split` with a null separator (spec-silent; returns the
single-element whole-string list on both engines — INTENDED).

**Hardened in CQL-12 EXPLORER (2026-Q2).** Query-produced `List<String>` values
passed to `Combine` must be folded into a DuckDB list before invoking
`Combine`/`CombineSep`; do not pass row subqueries directly to list macros. CQL
strings embedded into generated FHIRPath predicates, especially
`ext(element, url)`, must be escaped with FHIRPath backslash rules, not SQL quote
doubling. An escaped quote inside a URL must remain literal and must not be able
to inject `or true` or other predicate text into `extension.where(...)`.

### FHIRPath String Literal Unicode Escapes

**Discovered in FP-01 SKEPTIC literal audit (2026-05-16).** FHIRPath string literals support `\uXXXX` escapes where `XXXX` is hexadecimal. Keep the Python core string unescape path hex-aware and parity-tested against the C++ DuckDB extension. Numeric-only decoding silently corrupts literals such as `'\u00E9'` and `'\u03A9'` into `u00E9`/`u03A9` on the Python fallback while C++ returns the correct Unicode characters.

**Refined in FP-01 HISTORIAN literal audit (2026-05-16).** String unescaping must run as one left-to-right pass. Do not implement it as ordered global replacements: `\\` must yield one literal backslash without the produced backslash being reinterpreted as an escape for the next character. Regression examples: `\\p` returns `\p`, and `\u005Cp` returns `\p`.

### C++ Extension: Partial DateTime Timezone Validation

**Discovered in FP-01 HISTORIAN literal audit (2026-05-16).** DateTime literals may carry timezone offsets at hour, minute, or second precision, and offsets must use `(+|-)hh:mm` or `Z`. The C++ evaluator must validate and consume trailing timezone text at every DateTime precision; otherwise malformed values such as `@2014-01-25T14+99:99` can pass through as literal strings while the Python fallback returns empty. Keep `fhirpath_is_valid` false for malformed lexical shapes such as `@2014-01-25T14+09`.

### FHIRPath Empty Literal Operators and Singleton Boolean Evaluation

**Discovered in FP-02 SKEPTIC operator audit (2026-05-16).** DuckDB fallback syntax validation must preserve placeholder text when stripping string/date literals before malformed-expression checks; deleting a leading literal turns valid expressions such as `'x' & {}` and `'x' + {}` into apparent leading-operator expressions. FHIRPath singleton Boolean evaluation (§4.5) also applies to Boolean operators: a single non-Boolean node evaluates as true, empty propagates as empty, and multi-item inputs signal an error caught by DuckDB wrappers. Keep Python logical operators and native C++ `not()` parity-tested against this rule.

**Refined in FP-02 HISTORIAN operator audit (2026-05-16).** Keep strict core `iif()` criterion validation distinct from non-strict DuckDB wrapper resilience. Official R4 conformance `testIif6` expects strict semantic error for `iif('non boolean criteria', ...)`, but non-strict DuckDB fallback should match the native C++ wrapper for single-node FHIR fields such as `iif(gender, 1, 2)`. Use explicit strict-mode branching rather than globally weakening Boolean criterion validation.

**Refined in FP-02 EXPLORER operator audit (2026-05-16).** The Python DuckDB fallback must prefer the in-repo `fhir4ds.fhirpath` engine over external `fhirpathpy`; `fhirpathpy` can mishandle operand order and singleton truthiness for expressions such as `true and gender`, `zero and true`, and non-strict `iif(gender, ...)`. After C++ source fixes to singleton Boolean behavior, rebuild and copy the bundled `fhirpath.duckdb_extension`; otherwise public native UDFs can remain stale even when source tests look correct.

### FHIRPath Existence Functions Must Reuse Equality Semantics

**Refined in FP-03 HISTORIAN existence audit (2026-05-16).** `subsetOf()`, `supersetOf()`, `distinct()`, and `isDistinct()` are defined in terms of FHIRPath `=` equality. Keep Python core and native C++ implementations routed through semantic equality rather than string/repr/key-order comparisons. Regression cases: `1.combine(1.0).distinct().count() = 1`, structurally equal JSON objects with different member order are not distinct, and compatible quantities such as `1 'cm'` and `10 'mm'` compare equal for membership/distinctness. After C++ equality helper changes, rebuild and copy the bundled `fhirpath.duckdb_extension`.

### FHIRPath `repeat()` Must De-Duplicate Projection Results Only

**Refined in FP-04 HISTORIAN filtering/projection audit (2026-05-16).** `repeat(projection)` adds projection results while they are new according to FHIRPath `=` equality; it must not pre-seed the seen set with the input collection, and it must not add input seeds through type-specific shortcuts. Regression cases: `'a'.repeat($this)` returns `['a']`, `1.repeat(iif($this < 3, $this + 1, {}))` returns `[2, 3]`, and duplicate child objects produced by one projection evaluation are emitted once. After C++ `repeat()` changes, rebuild and copy the bundled `fhirpath.duckdb_extension`.

**Refined in FP-04 EXPLORER filtering/projection audit (2026-05-16).** The exported Python helper API in `fhir4ds/fhirpath/duckdb/functions/filter.py` must follow the same §5.2 semantics as the core engine and DuckDB UDFs. Keep `where()` strict to singleton Boolean criteria, propagate direct-helper `select()`/`repeat()` evaluator errors as `FHIRPathError`, keep helper `repeat()` projection-only with FHIRPath equality de-duplication, and resolve helper `of_type()` resource supertypes through model `type2Parent` metadata rather than exact Python-type checks.

### FHIRPath §6.3 Type Operators: Quantity Profile Subtype Rejection

**Fixed in FP-15 SKEPTIC iter 1 (2026-06-29).** Native C++ `fn_isType` at
`extensions/fhirpath/src/fhirpath/evaluator.cpp:8845` had an over-permissive
branch that treated ANY Quantity literal as matching the FHIR R4 profiles
`Age` and `Duration`. FHIR R4 defines `Age`, `Distance`, `Duration`, `Count`,
`Money`, and `SimpleQuantity` as profiles on `Quantity` that require specific
UCUM unit categories (e.g., Age uses calendar `a`/`yr` units; Duration uses
`s`/`min`/`h`/`d`/`wk`). A bare Quantity literal like `5 'mg'` (mass) is NOT
an Age or Duration. The pre-fix code inconsistently rejected `Distance`,
`Count`, `Money` (correct) but accepted `Age` and `Duration` (wrong).

Surgical fix at evaluator.cpp:8845-8851 removed `Age` and `Duration` from the
over-permissive branch; only `target == "Quantity"` now matches a literal
Quantity. The FHIR profiles must be matched via FHIR model metadata (not yet
implemented for runtime Quantity literals — future work).

Spec citations: FHIRPath v2.0.0 §6.3.1 ("is returns true if the type of the
left operand is the type specified, or a subclass thereof"); §4.1.8 (Quantity
literal is `System.Quantity`); FHIR R4 (Age/Distance/Duration/Count/Money/
SimpleQuantity are profiles with specific UCUM unit constraints).

Regression coverage: `test_quantity_literal_fhir_profile_subtypes_reject_in_both_backends_fp15_skeptic`
(10 cases) and `test_is_as_type_specifier_form_parity_fp15_skeptic` (15 paired
cases) in `fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py`.
After native changes, rebuild and copy the bundled `fhirpath.duckdb_extension`.

### FHIRPath §9-§12 Environment/Types/Type-Safety/Syntax — FP-20 SKEPTIC launch (2026-08-18, spec-compliance campaign)

**Zero CRITICAL/HIGH/MEDIUM new findings; CLEAN at iteration 1.** Probes:
`.temp/qa/fp20_skeptic2_probe.py` (core engine, 37 cases) and
`.temp/qa/fp20_skeptic3_probe.py` (dual-path, 32 cases, 0 parity diffs),
spec-grounded against FHIRPath 2018Sep §9-§12.

- DOCTRINE (%context, §9): `%context` is the ORIGINAL node passed to the
  engine and does NOT change with focus — `name.select(%context.id)` returns
  the original id on the core engine and both DuckDB paths. Docstrings in
  `fhir4ds/fhirpath/duckdb/context.py`/`evaluator.py` previously claimed
  otherwise (fixed). `with_focus()` only updates the focus used by
  focus-dependent helper evaluation, not spec-level %context.
- NOT A BUG (undefined env var, §9): the spec leaves undefined-environment-
  variable behavior open. Core `evaluate()` raises ValueError; DuckDB UDFs
  (native and fallback, parity verified) return empty and
  `fhirpath_is_valid` stays TRUE — env-var existence is a runtime concern,
  not syntax. Pinned by
  `test_environment_context_semantics_fp20.py::test_undefined_environment_variable_is_runtime_not_syntax_fp20`.
- INTENDED GAP (§10 metamodel): `type()` exposes only
  `{namespace, name}` (System/FHIR). `SimpleTypeInfo.baseType`,
  `ListTypeInfo.elementType`, `ClassInfo.element`, and `TupleTypeInfo` are
  unimplemented — navigation (`.baseType`, `.elementType`, `.element`)
  returns empty on BOTH engines. Official R4 fixtures (testType group) pin
  only `.namespace`/`.name`, so do not force-implement the STU metamodel
  without a fixture requirement. Shape locked by
  `test_environment_context_semantics_fp20.py::test_type_reflection_shape_fp20`.
- Host layer supplies `%resource`/`%rootResource` (and `%sct`/`%loinc`/
  `%ucum`/terminology vars) in the DuckDB UDF context; the core engine
  predefines `%context`/`%ucum`/`%sct`/`%loinc` and treats the rest as the
  §9 host extension point. Both `%\`name\`` backtick and `%'name'`
  single-quote forms are equivalent on both paths.
- §12 grammar: `FHIRPath.g4` matches the official N1 grammar on the FP-20
  productions (`externalConstant : '%' (identifier | STRING)`,
  typeSpecifier/qualifiedIdentifier, term/expression precedence); known
  deliberate deviations remain the FP-10 non-greedy STRING fix and the CQL
  LONGNUMBER superset.
- DRIFT (FP-20 QA-005, MEDIUM DEFERRED): 4 pre-existing dual-path failures
  in `test_environment_type_parity.py` (structural `qs.ofType(Quantity)` —
  the test docstring references an `structuralFHIRComplexType` helper that
  does not exist in evaluator.cpp at HEAD) and `test_type_parity.py`
  (`5 'mg' is FHIR.Quantity` → native true vs FP-15-pinned false;
  `recorded is FHIR.dateTime` → native true vs pinned false; temporal field
  specifiers). Same family as the FP-18 QA-007/FP-19 QA-003 three-way
  source/binary/test drift; queued for the FP-20 milestone-review
  reconciliation. Architectural note: native `fn_isType` uses
  field-name→type heuristics (name→HumanName, address→Address, ...) while
  the Python fallback uses value-shape structural inference
  (`TypeInfo.create_by_value_in_namespace`) — two divergent heuristic
  strategies for the same §6.3/§10 seam that the reconciliation chunk must
  unify.

### FHIRPath §9-§12 — FP-20 HISTORIAN launch (2026-08-18, spec-compliance campaign)

**Second personality on §9–§12 (120+ fresh dual-path probe cases in
`/mnt/d/fhir4ds/.temp/qa/fp20_historian{2,3,4}_probe.py`): 1 MEDIUM fix,
0 parity diffs after fix.** Spec grounding: fetched 2018Sep spec text for
trace()/type()/logical-operator/division semantics and the official
2018Sep `FHIRPath.g4` (compared against repo grammar).

- FIXED (QA-001, MEDIUM — parity + §10/§12 typing): `Meta.profile` is
  `canonical` and `Meta.source` is `uri` per R4, but native
  `fhirFieldType` (evaluator.cpp) hardcoded profile→uri and omitted
  source, while the Python fallback suffix table
  (`fhir4ds/fhirpath/models/r4/fhir_path_to_type.json`) lacked both —
  `meta.profile.type().name` was native `uri` vs fallback `string`. Fix:
  added `.profile`/`.source` suffix entries (canonical→uri subtype chain
  already in type2Parent) and aligned fhirFieldType
  (profile→canonical, source→uri); extension rebuilt + redeployed. Locked
  by `test_uri_type_reflection_parity_fp20.py`.
- NOT A BUG (§12 grammar): non-empty literal collection construction
  `{1, 2}` is a syntax error that CONFORMS — the official 2018Sep grammar
  `literal : '{' '}'` has no non-empty literal-list production (the 2025
  N1 grammar adds list literals; out of R4 scope). Also `List<T>` type
  specifiers are absent from the official `typeSpecifier` rule, so
  `name is List<FHIR.HumanName>` must be a syntax error.
- NOT A BUG (spec-verified semantics): `trace()` returns its INPUT
  collection unchanged (so `trace('t',1)+1` errors, correct);
  `type()` on a multi-item collection returns per-element TypeInfo
  (spec example `('John'|'Mary').type()`); `true and 1` → true via
  Singleton Evaluation of Collections; div/0 behavior unspecified in
  2018Sep (empty result acceptable).
- OPERATIONAL HAZARD (FP-20 HISTORIAN, 2026-08-19): sibling campaign
  sessions share this working tree, the bundled extension path, and the git
  index — a race overwrote this launch's evaluator.cpp edits mid-run and
  deadlocked .git/index.lock (stray stuck `git` processes). Before final
  validation, re-verify source markers (grep for the fix comment), rebuild,
  and confirm behavior through a FRESH process's reloaded extension.
- KNOWN APPROXIMATION: `.system` suffix maps to `uri` on both engines
  although ContactPoint.system is `code` (Identifier.system is uri) —
  shared, fixture-unpinned, no parity divergence. Do not "fix" one side
  without the other.

### FHIRPath §9-§12 — FP-20 EXPLORER launch (2026-08-19, spec-compliance campaign)

**Third personality on §9–§12: ZERO findings; chunk CLOSED CLEAN after three
consecutive clean launches (SKEPTIC, HISTORIAN, EXPLORER).** 131 fresh
dual-path (native extension vs forced Python fallback) probe cases in
`/mnt/d/fhir4ds/.temp/qa/fp20_explorer2_2026_08_19/` — 0 parity diffs,
0 spec violations.

- VERIFIED CLEAN: %context/%rootResource original-node invariant under
  `select`/nested-`select`/`where`/`repeat`/`first()`/deep navigation, incl.
  two-level `contained` nesting — %resource/%rootResource stay the ROW
  resource (spec-correct: they track the resource containing the ORIGINAL
  node, not the navigated focus; the FHIR "contained resource is the focus"
  case only arises host-side, never via in-expression navigation).
- VERIFIED CLEAN: %ucum/%sct/%loinc available; backtick `%\`name\`` and
  single-quote `%'name'` env-var forms identical; undefined env vars
  classify identically on both engines.
- VERIFIED CLEAN: uri-family `type()`/`is`/`as` chains on canonical/uri/oid/
  uuid system values, instant, code, contentType, unqualified type
  specifiers (`is uri`, `as code`) — HISTORIAN's Meta.profile→canonical /
  Meta.source→uri fix intact, 0 parity diffs.
- VERIFIED CLEAN: §11 type-error surfaces through parents (`(1='a')` empty
  under and/or/not/implies/=/iif; `1+'a'` error → empty through `|` and
  `combine()`; `5 'cm' = 5 'kg'` empty); §12 grammar oddities (6-deep parens,
  CR/LF/TAB and whitespace around `.`/`(`/`)` in expressions passed through
  DuckDB SQL strings, `\uXXXX` escapes).
- NOT A BUG (as-exact asymmetry reconfirmed): `status is string` → true but
  `status.as(string)` → empty is the FP-15 HISTORIAN fixture-pinned doctrine
  (official R4 fixtures pin `as`/`ofType` EXACT for primitives although
  2018Sep §6.3 prose is subtype-inclusive; fixtures outrank prose).
- NOT A BUG (tuple literals): `{a: 1}` is a syntax error that CONFORMS — the
  official grammar (2018Sep AND N1) has `literal : '{' '}'` only; there is
  NO tuple literal production. Do not "add" tuple support without a fixture
  or grammar change upstream.
- NOT A BUG (%terminologies/%environment): FHIR-spec-added env vars are a
  host extension point; without a configured terminology service they are
  undefined → empty with consistent error classification on both engines.
  `environment()` is not a FHIRPath function.

### FHIRPath §6.4 Collections — FP-16 SKEPTIC launch (2026-08-18, spec-compliance campaign)

**Fixed in FP-16 SKEPTIC iter 1 (2026-08-18).** Exported helper
`fhir4ds/fhirpath/duckdb/operators.py::membership()/contains()` swallowed
multi-item singleton-operand violations by returning `{}`, while the core
engine (`engine/invocations/collections.py`) and native `evaluator.cpp` raise
`FHIRPathError`. Per §6.4.2/§6.4.3 a multi-item singleton operand must throw.
Helpers now raise the exact engine messages ("in requires the left operand…"
/ "contains requires the right operand…"), which already exist in the native
source and error-classification contract, so no udf/native edits were needed.
12th instance of the "exported helper API forgotten" family; the family's
signature is a silent `return FHIRPathCollection([])` on a non-singleton
guard. Regression: `test_membership_helper_singleton_violations_raise_fhirpath_error`
in `fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py`.

Verified clean (no code change needed): union dedups at construction via `=`
(`1|1.0`→1, `1 'cm'|10 'mm'`→1, deep `(name|name)`→1, combine-then-union
dedups); `in` left-empty→empty, right-empty→false, multi-left→error;
`contains` right-empty→empty, left-empty→false, multi-right→error;
quantity/temporal/deep equality through membership; contains-operator vs
contains(substring)-function disambiguation; `1 + 2 | 3` §6.8 precedence.
Probe: `.temp/qa/fp16_skeptic_probe.py` (37 dual-path cases, 0 parity diffs).

### FHIRPath §6.4 Collections — FP-16 EXPLORER launch (2026-08-18, spec-compliance campaign)

**Zero findings; chunk CLOSED CLEAN after 3 personality launches.** EXPLORER
boundary-combination pass (`.temp/qa/fp16_explorer2_probe.py`, 51 fresh
dual-path cases; conformance 2832/2832 held). All clean on BOTH engines:
multi-operand union chains preserve first-occurrence dedup order
(`(3|1|3|2|1|4)`→`[3,1,2,4]`, confirmed at engine AND helper level); union
seeds into `repeat()` follow FP-04 projection-only dedup; error-typed operands
(`1/0` is `{}`, `(1/0) in X`→empty — membership never spuriously errors);
heterogeneous collections; `in`/`contains` results feeding `and`/`or`/`iif()`;
null-element dedup/membership; temporal partial-precision membership at
year/month/day/hour/minute/Time pairs; quantity unit-family membership and
calendar-vs-UCUM both directions; deep struct dedup with `$this` membership.
Behavior pins (NOT A BUG): inside `where()`/`select()` a bare identifier
navigates from `$this` (`obs.where($this in obs)`→0 — `obs` resolves to
`$this.obs` = empty, not the outer collection); `'final'.contains('in')` is
the substring FUNCTION (true — f-i-**in**-al); multi-item `in` left operand
raises at core/helpers but is converted to NULL by the DuckDB wrapper
(row resilience, established intent). Methodology: normalize boolean output
case before comparing probe expectations (`'true'` vs `True` produced 30+
phantom EXPECT-FAILs in the probe harness itself).

### FHIRPath §6.4 Collections — FP-16 HISTORIAN launch (2026-08-18, spec-compliance campaign)

**Zero findings; chunk closed CLEAN.** HISTORIAN confirmation pass
(`.temp/qa/fp16_historian_probe.py`, 30 fresh dual-path cases + 8-case
helper-API audit; conformance 2832/2832). Re-verified SKEPTIC's helper fix
intact and message-identical. New ground verified clean on BOTH evaluation
paths: §5.4.1 `union()` FUNCTION form is a true synonym of `|` (dedup across
operands, empty input/arg, Integer=Decimal, deep objects); precision-mismatch
equality flows correctly through dedup (`(@2012-01 | @2012)`→2) and
membership (`@2012-01 in (@2012|@2013)`→false because empty≠True); singleton
operands (`1 in 1`→true, `1 contains 1`→true); calendar-vs-definite-duration
dedup (`1 year | 1 'a'`→2 per §6.1.1, `1 second | 1 's'`→1); membership
inside `where`/`select` with `$this`; grammar edges (`1|2` no-space,
`1 in(1|2)`); §5.1.8/9 subsetOf/supersetOf `=`-membership consumers
(supersetOf over a duplicated `other` is correctly true — membership, not
multiset equality).

### FHIRPath §6.5 Boolean Logic — FP-17 SKEPTIC launch (2026-08-18, spec-compliance campaign)

**Zero findings; chunk CLOSED CLEAN at iteration 1.** 140-case dual-path probe
(native extension vs forced Python fallback; `.temp/qa/fp17_skeptic/probe.py`
+ round-2 battery) verified: full 3VL truth tables for `and`/`or`/`xor`/
`implies` (true/false/{} x true/false/{}) via literals AND resource fields;
short-circuit cells (false and {}→false, true and {}→{}, true or {}→true,
false implies X→true incl. false implies {}=true, {} implies true→true,
{} implies false/{}→{}); fixture anchoring (testBooleanLogicXOr1-9,
testBooleanImplies1-9 match exactly); §6.8 precedence and>or=xor(left-assoc)>
implies; multi-item operands raise in core/helpers and become wrapper NULL on
BOTH engines (row resilience intent); exported `operators.boolean_*` helpers
raise on multi-item and match core tables (no new "exported helper API
forgotten" instance); `fhirpath_is_valid` classifies `1 and true` /
`'x' implies 5` as VALID (runtime typing, not syntax) and bare `not(...)` as
INVALID. Conformance 2832/2832 held.

### FHIRPath §6.5 Boolean Logic — FP-17 HISTORIAN launch (2026-08-18, spec-compliance campaign)

**Zero findings; second consecutive clean launch — chunk CLOSED CLEAN.**
56+10 case dual-path probe (`.temp/qa/fp17_historian_2026_08_18/probe.py`),
new angles beyond SKEPTIC: chained-implies associativity, boolean logic
inside where/select/iif/exists/all, rich comparisons (dates, !=, in, 1/0)
feeding boolean ops, not() arity misuse, $this iteration, explicit JSON null
vs absent fields, deep nesting. 0 parity diffs, 0 spec violations.

NOT-A-BUG registry additions (Historian grammar trap):
- **Chained `implies` is LEFT-associative and correct.** The official FHIRPath
  ANTLR grammar puts and/or/xor/implies in one left-recursive expression rule
  (alternative order gives precedence tiers, all left-assoc; mirrored in
  `fhir4ds/fhirpath/parser/FHIRPath.g4`). `false implies false implies false`
  = false (= `(false implies false) implies false`). CQL's separate
  `implicationExpression` right-recursion does NOT apply to FHIRPath — do not
  import CQL associativity assumptions here.
- Unqualified identifiers inside where()/select() resolve against `$this`
  (the item), not the resource root: `names.where(primary and t)` → [] because
  `t` → item.t = {} → `primary and {}` = {}.
- `not()` at root: focus = the resource itself (truthy non-boolean singleton
  per §4.5) → false. Bare `not(...)` with any nesting errors → wrapper NULL
  (function-form-only pin reconfirmed).
- `t.not(false)` (wrong arity) → is_valid=false; `not()` (0 args, implicit
  focus) → is_valid=true; consistent on both engines.
- `any()` is not a FHIRPath function (CQL-ism) — correctly unknown → empty.
- Observation (out of chunk): string-rhs `in` (`'hello' in s`) → true on both
  engines; spec does not define string membership; engines agree.

Conformance 2832/2832 held. Permanent parity guard:
`fhir4ds/fhirpath/duckdb/tests/integration/test_boolean_logic_parity.py`
(53 assertions green).

NOT A BUG pins: `not` is function-form only (`X.not()`); bare `not(true)`
is invalid grammar → empty, `fhirpath_is_valid`=false. Non-boolean singletons
are truthy through all boolean operators per the §4.5 FP-02 doctrine.
`xor` chains are left-associative: `true xor false xor true` → false.
Unequal non-empty comparisons are `false`, not empty: `(s='nope') and true`
→ false. The SQL macros in `fhirpath/duckdb/macros/logical.py` are legacy
CQL-adjacent surface, not the FHIRPath operator path; their `Implies` table
already matches §6.5.

### FHIRPath §6.6/§6.7 Math + Date/Time Arithmetic — FP-18 HISTORIAN launch (2026-08-18, spec-compliance campaign)

Fresh divergence hunt after the FP-18 SKEPTIC fixes (re-verified intact: exact
int64 div/mod, native Integer div rendering, exact Decimal mod, unsuffixed
>INT32 literal errors, Quantity div/mod + 'a'/'mo' temporal error contracts).
Probe: `.temp/qa/fp18_historian2_2026_08/{probe,drill}.py` (95 three-engine
cases). Conformance 2832/2832 held; fhirpath unit tree 66/66 in
test_fp18_math_operators.py.

Fixed (both mirrored where applicable; extension rebuilt + redeployed):
- **Native §6.7 Time ± Quantity result rendering (QA-002, MEDIUM):**
  `fn_dateArith` stored the Time result with a leading `T` while every other
  native Time path stores bare `hh:mm:ss[.fff]` (§5.5.8 Time toString has NO
  `T`; Time literals render without it on BOTH engines). `'@T10:30 + 90
  minutes'` now renders `12:00`/`10:31:00`-style, parity with fallback.
  DOCTRINE: Time FPValue.string_val NEVER carries the leading `T`.
- **Integer minimum literal (QA-006, LOW):** §4.1.3's minus sign is unary
  negation, not part of the literal, so `-2147483648` (INT32_MIN) is a valid
  Integer. Core's `number_literal` range check fired on the unsigned literal
  before negation; `polarity_expression` now special-cases unary minus over
  the exact 2^31 NumberLiteral (mirrors the existing
  `-9223372036854775808L` Long convention). Bare `2147483648` and
  `-2147483649` still raise.

NOT A BUG registry (fixture-pinned — GREP tests-fhir-r4.xml BEFORE treating
§6.7 prose as binding; a name-filtered grep for "testDate" misses the
testPlusDate* family):
- **UCUM definite durations above seconds ARE valid §6.7 units** (`'d'`,
  `'wk'`, `'h'`, `'min'`, `'s'`, `'ms'`): fixtures testPlusDate13/15/18-22
  pin them as valid; only `'mo'`/`'a'` are execution-invalid
  (testPlusDate14/16). The §6.7 prose "definite-duration above seconds →
  error" is overridden by fixtures.
- **Fractional time-valued quantities truncate** even at second
  precision: testPlusDate19 pins `+ 0.1 's'` on a ms-precision DateTime as a
  NO-OP; testPlusDate2 pins `+ 7.7 days` truncation. Do not "fix"
  `+ 1.5 seconds` to carry `.5`.
- **Integer arithmetic overflow degrades to the exact Decimal value**
  (`2147483647 + 1` → `2147483648.0`) instead of §6.6's "overflow → empty":
  documented cross-engine doctrine (`_numeric_arithmetic_result` in
  engine/invocations/math.py; FP-11 power() doctrine comment). Both engines
  behave identically.

DEFERRED (QA-001, MEDIUM — needs a dedicated native UCUM port chunk): native
Quantity `+`/`-`/`*`//` composes results in SI base units (`3 'm' + 3 'cm'`
→ `3.03 'm'`, `12 'cm' * 3 'cm'` → `0.0036 'm2'`, `3 'cm' * 12 'cm2'` →
non-canonical `0.000036 'm.m2'`) while the spec examples and Python fallback
use operand-unit-space composition with most-granular-unit results
(`303 'cm'`, `36 'cm2'`, `4.0 'cm'`; see `_parse_unit_exponents`/
`_render_unit_exponents` + FP-02 HISTORIAN selection in nodes.py). Values are
semantically equal and no fixture pins the rendered unit (testQuantity9
compares via base-reduced equality and passes on both engines). Fix requires
porting the UCUM term-exponent algebra to evaluator.cpp.

### FHIRPath §6.3 is/as — fresh FP-15 SKEPTIC launch (2026-08-18, spec-compliance campaign)

121-case dual-path probe (fixture testType5–23/testTypeA*-anchored,
`.temp/qa/fp15_skeptic2_2026_08_18/probe.py`). Five fixes, all RESOLVED;
fhirpath tree 1914 passed, conformance 2832/2832 held.

- **Fallback hierarchy merge order (QA-001, HIGH):** `TypeInfo.
  FHIR_TYPE_HIERARCHY` (engine/nodes.py) merged legacy
  `fhir_type_hierarchy.json` OVER canonical `type2Parent.json`, whose
  uuid→string/uri→string flattenings erased the uri ancestor —
  `valueUuid is FHIR.uri` was false on the fallback while fixture testTypeA4
  pins true. Canonical now wins; documented conventions kept as explicit
  overrides (uri→string, Money→Quantity, Dosage/Timing→Element). DOCTRINE:
  canonical type2Parent.json is the source of truth; legacy tables may only
  ADD conventions, never erase canonical parent edges.
- **Native qualified FHIR.Quantity literal match (QA-002, HIGH):** evaluator.cpp
  `fn_isType` literal-Quantity branch ignored `explicit_namespace`, so
  `5 'mg' is FHIR.Quantity` was true natively. Now `!explicit_namespace` —
  unqualified `is Quantity` keeps the shared true convention (both engines),
  FHIR-qualified does not (testType12/14 namespace doctrine). Extension
  rebuilt + redeployed. ENVIRONMENT TRAP (repeated): a background `make
  fhirpath_loadable_extension` raced the source edit and shipped a stale
  binary — after rebuilding, VERIFY the fix through the reloaded extension
  before concluding; `touch evaluator.cpp` + rebuild if needed. Also: grep on
  evaluator.cpp is binary (embedded NUL) — use `grep -a`/`tr -d '\000'`.
- **Choice-rescue hijack of non-choice fields (QA-003, HIGH):** the udf.py
  choice-assertion rescue OVERRIDES correct non-empty engine results whenever
  its regex+lookup matches; the bogus single-option CHOICE_TYPES entries
  (Resource.contained=containedResource, Observation.subject=subjectReference,
  …) made `contained is/as(T)` return empty/false on the fallback.
  `_get_choice_type_lookup` now skips len<=1 entries (mirrors fhir_model.py).
  RESIDUAL DRIFT (ARCH-001): rescues can still mask engine results for real
  choice fields; guard-on-empty or delete when the engine covers choices.
- **Exported typecheck helpers (QA-004, MEDIUM, 11th "exported helper API
  forgotten" instance):** `functions/typecheck.py is_type/as_type` string
  specifiers never resolved unqualified System names (`5 as Integer` → []).
  They now mirror the engine parser's namespace resolution; the distinct
  System-name list is hand-duplicated from native `isDistinctSystemTypeName`
  (keep in lockstep).
- **is/as type-specifier invocation is invalid syntax (QA-005, LOW):**
  `X is FHIR.Quantity.not()` is rejected by the native grammar (typeSpecifier
  is not an expression) but the lenient fallback accepted it. New
  `_INVALID_TYPE_SPECIFIER_INVOCATION` precheck in udf.py (string-masked, both
  `_get_compiled_evaluator` and `fhirpath_is_valid_udf`) aligns the surfaces.
- NOT A BUG pins: `id is FHIR.string` true (id derives from string per R4);
  unqualified `valueQuantity is Quantity` true (shared convention);
  `active as Boolean` empty (FHIR.boolean ≠ System.Boolean); `(1 as Decimal)
  = 1.0` empty (`as` asserts, never converts); `5 is Bogus`/`5 as Bogus`
  empty on both (unknown-type doctrine); telecom.system typed FHIR.uri
  (name-only metadata limit, REV-002 family — QA-006 INTENDED).
- Regression tests: `test_type_parity.py` `*_fp15_skeptic2` (5 tests).

### FHIRPath §6.3 `as` exact-vs-subtype — FP-15 HISTORIAN launch (2026-08-18, spec-compliance campaign)

78-case dual-path probe + drills (`.temp/qa/fp15_historian_2026_08_18/`).
CRITICAL DOCTRINE CONFIRMED: official R4 fixtures pin an `is`/`as`
ASYMMETRY on FHIR primitives — `is` is subtype-based
(testFHIRPathIsFunction: `Patient.gender is string` TRUE, code <: string),
but `as`/`ofType` are EXACT-match for primitives
(testFHIRPathAsFunction11: `Patient.gender.as(string)` EMPTY — missing
<output> IS an expected-EMPTY assertion; AsFunction12 `.as(code)` -> male;
AsFunction13 `.as(id)` EMPTY; `ValueSet.version.as(code)` EMPTY).
Fixtures outrank §6.3 prose ("or a subclass thereof"), which reads as
subtype for both. FP-20's `as Element` empty gate is therefore REQUIRED,
not temporary. Lesson: when validating a §6.3 hypothesis, grep fixtures
for FUNCTION-form spellings too (`as(string)`, `is(uri)`) — a grep for
`as [A-Z]` misses the whole testFHIRPathIs/AsFunction group.

- **QA-001 HIGH -> INTENDED (fixture-pinned, change reverted):** an initial
  dual-engine "fix" made `as` subtype-based; the FHIRPath conformance suite
  caught it (934/935, testFHIRPathAsFunction11). Fully reverted in
  `engine/invocations/types.py as_fn` and native `fn_asType` (extension
  rebuilt + redeployed; md5 e44604b5 was superseded, final binary rebuilt
  from reverted sources). A fix that looks spec-perfect can still be
  fixture-wrong — run the conformance suite BEFORE handoff, not after.
- **ARCH-001 guard-on-empty implemented (fallback, kept):** udf.py choice
  rescues (`_resolve_choice_type_assertion`,
  `_resolve_trailing_choice_type_assertion`) previously OVERRIDES the engine
  result unconditionally on a regex+lookup match, and their op=`as` miss
  paths returned [], clobbering correct non-empty engine results (observed:
  `parameter[0].value as FHIR.string` while the subtype experiment was
  live). All op=`as` miss paths now return None (defer to engine). With the
  fixture doctrine restored this is a no-op behaviorally, but it removes the
  clobbering class permanently. DOCTRINE: rescues may only supply a value
  they actually resolved; on a miss, defer (None), never [].
- **Fallback `implicitRules` typed string (QA-002, MEDIUM, FIXED):** native
  curated `fhirFieldType` maps implicitRules->uri, but
  `fhir4ds/fhirpath/models/r4/fhir_path_to_type.json` (engine-side,
  mirrors `fhir_model.py:_get_common_path_to_type_mappings` which HAS it)
  lacked the entry, so the fallback value-shape-inferred FHIR.string:
  `implicitRules is FHIR.uri` native true / fallback false. Added
  `".implicitRules": "uri"` (data-driven metadata).
- **abatementBoolean LOW INTENDED:** R4 Condition.abatement[x] has NO
  boolean arm; on non-conformant `{abatementBoolean}` input native's
  generic `abatement*` key scan says true, fallback (CHOICE_TYPES
  metadata) says empty. Native leniency documented; no fix.
- ENVIRONMENT NOTE: literal `is`/`as` probes MUST pass a real resource to
  `fhirpath(resource, expr)` — a NULL resource returns EMPTY for literal
  expressions on BOTH engines (udf contract); probing with NULL focus
  fakes failures.
- Regression tests: `test_type_parity.py` `*_fp15_historian` (2 tests:
  is/as asymmetry pins + implicitRules uri typing).

### FHIRPath §6.3 is/as chains + R4 instant fields — FP-15 EXPLORER launch (2026-08-18, spec-compliance campaign)

121-case dual-path probe + 2 drills (`.temp/qa/fp15_explorer2_2026_08_18/`).
Three fixes, one deferral; fhirpath tree 1918 passed, conformance 2832/2832 held.

- **Native infix is/as CHAIN defect (QA-001, HIGH, FIXED):** official
  FHIRPath.g4 rule `expression ('is' | 'as') typeSpecifier #typeExpression`
  is LEFT-RECURSIVE, so chains like `Patient as Resource is FHIR.Patient`,
  `Patient is Resource is Boolean`, and `A as T as U` are valid official
  syntax with LEFT associativity. Native `parser.cpp parseTypeExpression`
  consumed at most one typeSpecifier (single-shot `if`), yielding EMPTY for
  any chain while the Python fallback evaluated correctly. Fixed with a
  while-loop; extension rebuilt + redeployed (bundle AND user site-packages).
  DOCTRINE: when mirroring the ANTLR grammar in the hand-rolled
  recursive-descent parser, LEFT-RECURSIVE rules become LOOPS, not `if`s —
  audit other recursive grammar rules for the same flattening.
- **R4 instant-typed fields (QA-002/QA-003, MEDIUM, FIXED):** AuditEvent/
  Provenance.recorded and Meta.lastUpdated are FHIR `instant` (sibling of
  dateTime, not a supertype). `recorded` was typed string on both engines;
  `lastUpdated` was dateTime natively (a native/fallback parity diff).
  Fixed in evaluator.cpp fhirFieldType + models/r4/fhir_path_to_type.json +
  duckdb/fhir_model.py (all three curated copies, ARCH-002 doctrine). The
  fallback used SUFFIX keys (".recorded", ".lastUpdated") deliberately: they
  keep name-only semantics IDENTICAL to native fhirFieldType, so no parity
  break. Prefer suffix keys over per-resource keys when native lacks path
  awareness.
- **Per-path type gap (QA-004, LOW, DEFERRED):** ValueSet.url canonical,
  Condition.note.text markdown, Claim.total Money, Encounter.length Duration,
  Narrative.div xhtml all type-check as their base primitive on BOTH engines
  (parity holds). Native fhirFieldType is name-only and cannot express them;
  fixing only the fallback (which has per-path keys) violates dual-engine
  lockstep. Needs path-aware native field typing or the ARCH-002 single
  generated metadata source.
- NOT A BUG pins: `div` is a reserved keyword (integer division) — `text.div`
  is a syntax error; use `text.\`div\``. `(gender | id) is FHIR.string` EMPTY
  is correct (multi-item focus; §6.3 singleton rule). `contained is T` on
  multi-item contained is EMPTY for the same reason; use
  `contained.select($this is T)` or `ofType`. defineVariable expressions were
  rejected by the udf pattern precheck on BOTH engines (pre-existing, not §6.3).
- Regression tests: `test_type_parity.py` `*_fp15_explorer` (2 tests, 16 cases).

### Architecture Drift Log — FP-15 HISTORIAN (2026-08-18)

- **ARCH-002 (open):** field-name→primitive-type knowledge exists in THREE
  curated copies that can drift independently: native `fhirFieldType`
  (extensions/fhirpath/src/fhirpath/evaluator.cpp),
  `fhir4ds/fhirpath/duckdb/fhir_model.py:_get_common_path_to_type_mappings`,
  and `fhir4ds/fhirpath/models/r4/fhir_path_to_type.json` (engine side).
  FP-15 HISTORIAN QA-002 was an instance (2 of 3 had `implicitRules: uri`;
  the engine JSON did not, so the fallback value-shape-inferred string).
  Consolidate to a single generated source when next touching model
  metadata; any new field-type entry must land in all three meanwhile.
- **ARCH-001 (bounded):** udf.py choice-assertion rescues are regex
  heuristics layered over the engine. FP-15 HISTORIAN applied
  guard-on-empty (op=`as` miss paths return None / defer to engine), so
  they can no longer clobber non-empty engine results; full deletion still
  awaits engine-side choice coverage for all CHOICE_TYPES fields.

### FHIRPath §4.1.8 Quoted Calendar Duration Keyword Literals

**Found in FP-01 SKEPTIC fresh rerun (2026-08-16); FIXED in iteration 1.** Per
FHIRPath N1 §4.1.8, a Quantity literal's unit may be a single-quoted UCUM unit
OR a single-quoted calendar duration keyword, singular or plural
(`4 'year'`, `2 'days'`); the spec's Time-valued Quantities table defines
`'year'` etc. as the *unit representation* of the calendar keywords, so
`1 'month'` and `1 month` are the same quantity. The native C++ path handles
this correctly because the lexer stores STRING units unquoted ("month"), so
quoted keywords fall into the calendar tables naturally. The Python engine
stored quoted units WITH quotes (`FP_Quantity.unit == "'month'"`), causing:
`1 'month' = 1 month` → False (should be True), `1 'month' = 1 'mo'` /
`1 'year' = 1 'a'` → True (should be empty — calendar vs UCUM year/month are
not comparable), quoted PLURAL keywords rejected in date arithmetic
(`@2015-02-04 + 2 'days'` error while native returns `2015-02-06`), and
display divergence (`4 'year'` vs `4 year`). Fix: canonicalize the 16 quoted
keyword spellings to bare form at `FP_Quantity` construction
(`fhir4ds/fhirpath/engine/nodes.py`); never canonicalize genuine UCUM units
(`'a'`, `'mo'`, `'wk'`, ... are NOT keyword spellings). Regression coverage in
`fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py`.

**Calendar conversion factors (§5.5.7) for unanchored comparisons — FIXED
same iteration.** `1 month = 30 days` and `1 year = 365 days` (N1 §5.5.7
factors, "only used when time-valued quantities appear in unanchored
calculations", applied per §6.1.1/§6.2 "the calendar durations as defined in
the toQuantity function") are now TRUE in both engines, and ordering follows
the factors (`1 month > 29 days` true; `1 month > 30 days` false; `1 year >
365 days` false). CRITICAL design constraint: the spec table is month-based
for year↔month pairs (`1 year = 12 months`) and day-based for year/month vs
day-and-below (12 × 30 days = 360 days ≠ 365 days), so NO single
seconds-per-unit mapping satisfies every row. Therefore year↔month pairs
(including `'a'`/`'mo'`) must compare in MONTHS, while cross-group pairs
convert the calendar keyword operand with explicit 2592000 s / 31536000 s.
UCUM `'mo'`/`'a'` keep their mean-duration seconds: `1 'mo' = 29 days` stays
false, `1 'mo' > 29 days` stays empty (§6.2), `1 month = 1 'mo'` stays empty
(§6.1.1). A calendar year/month KEYWORD versus a UCUM week/day/time code IS
comparable (`30 'd'` is exactly 30 days → `1 month > 29 'd'` true).
Implementation: Python `FP_Quantity._unanchored_duration_seconds` +
`_year_month_ucum_units` used by `equality.py::_quantity_base`, `FP_Quantity
.__eq__`/`deep_equal`/`compare`; native `yearMonthMonthsFactor` +
`unanchoredDurationSeconds` in `quantityEqualState`,
`quantityEquivalentState`, `quantityValuesEqual`, and the §6.2 ordering site,
plus a `isMixedCalendarUcumDurationAboveSeconds` exception. The shared
`extensions/fhirpath/src/include/shared/ucum_units.hpp` table is BYTE-IDENTICAL
(FHIRPath-specific semantics live at the comparison sites, so the CQL extension
required no rebuild and CQL conformance held 1706/1706); toQuantity
(`(1 year).toQuantity('month')` → `12 month`) and quantity arithmetic/division
(`1 month / 1 day` → `30.436875 '1'`) deliberately keep the UCUM-table
semantics in both engines.

**Unary minus on decimal zero must normalize to 0.0 (QA-005).** The official
R4 test `HighBoundaryDecimal16` (`-0.0034.highBoundary(1)` → `0.0`; the unary
minus applies to the zero-valued boundary result because `.` binds tighter
than unary `-`) requires `-0.0` to render as `0.0`. Python's Decimal unary
minus already normalizes negative zero; the native `evalUnaryOp` Decimal AND
Quantity branches were fixed to normalize the value and source_text. Lesson:
when a parity divergence involves display/precision, check the official
fixtures for the authoritative direction BEFORE choosing which engine to
change — engine parity never overrides an official expectation.

**Conformance harness SQL adapters must not append clauses to generated SQL
tails (QA-008).** The ViewDefinition conformance adapter
`conformance/scripts/run_viewdef.py::_add_resource_type_filter` appended
`AND <filter>` to any UNION branch containing a line-starting WHERE; for
`repeat` inside `forEachOrNull` the only WHERE lives inside the LATERAL
subquery, so the AND dangled after `) as ..._table` and DuckDB rejected the
SQL — even though the raw generated SQL returns exactly the expected rows
(verified by executing it directly). The adapter now pushes the resourceType
predicate into every `FROM resources t` reference. Lesson: when a conformance
run reports generated-SQL syntax errors, execute the raw generator SQL first
to decide whether the bug is the generator or the harness.

**FP-01 HISTORIAN iter 1 (2026-08-16): mixed calendar-vs-UCUM year/month
equality is EMPTY — the official fixtures outrank the spec prose, in BOTH
directions.** N1 and published v3.0.0 §6.1.1 prose say these pairs are
"considered unequal" (`1 year = 1 'a'` // false) and §4.1.8 says "1 year is
not equal to 1 'a'", but the official R4 fixtures
`testStringQuantity{Month,Year}LiteralToQuantity`
(`'1 'a''.toQuantity() = 1 year`) carry NO `<output>` element — which the
conformance harness reads as **expected empty** (a missing `<output>` is a
fixture contract, never "unspecified"). A prose-literal fix (false/!= true)
was implemented in both engines, broke those 2 official tests (933/935), and
was fully reverted per the Recovery Gate. Guard test
`test_mixed_calendar_ucum_year_month_equality_is_empty_fp01_historian`
in `test_literal_parity.py` pins the empty semantics with the escaped-quote
toQuantity fixture forms plus literal equivalents, ordering-empty (§6.2), and
equivalence-true (§6.1.2) guards. Lesson: when grepping fixtures for a
behavior, treat absent `<output>` as an explicit expected-empty assertion.

**Time arithmetic results are canonical T-less Time values (FP-01 HISTORIAN
QA-002).** Per the §5.5.1 toString() representation table (Time →
`hh:mm:ss.fff(+|-)hh:mm`), the `@T` prefix is literal syntax only, never
value form: `(@T14:34:28 + 30 'minutes').toString()` → `15:04:28` in both
engines, the native result storage matches `normalizeTimeLiteralString`
(no manual "T" prepend), and the Python `_plus_time` returns an `FP_Time`
node (not a raw string), so arithmetic results keep Time-type semantics
(`result = @T15:04:28` true; `result = '15:04:28'` empty per §5.5
String→Time Explicit-only). The §6.7 partial-time truncation rule
(`@T14 + 30 'minutes'` → `14`) is unchanged.

**Time literals compared with plain Strings are empty in both engines
(FP-01 HISTORIAN QA-003).** `@T14:34:28 = '14:34:28'` → empty (§5.5:
String→Time conversion is Explicit-only; §6.1.1 requires same type or
implicit conversion). The Python fallback's `datetime_equality` no longer
coerces plain non-ResourceNode strings against `FP_Time` peers.
Date/DateTime-vs-plain-string coercion (`@2015-02-04 = '2015-02-04'` →
true in both engines) is a deliberate shared JSON-convenience convention
that deviates from the strict §5.5 reading; it is intentionally unchanged
(no fixture pins it; narrowing it risks JSON temporal-field comparisons)
and documented here as intended behavior.

**FIXED: native binary64 Decimal arithmetic vs Python Decimal fallback
(FP-01 EXPLORER QA-001/QA-002, 2026-08-16).** Native plain-number `+`/`-`/
`*` (`evaluator.cpp` evalBinaryOp numeric path) computed in double and
re-rendered at a fixed decimal scale, so decimals with >16 significant
digits were corrupted by identity operations (`0.6666666666666666 * 1` →
`0.66666666666666663`), and division rendered the binary64 quotient
(16-17 digits, scientific notation leaked into `fhirpath_json`, 10^19
integer-digit loss), producing OPPOSITE equality/ordering booleans across
engines (`2.0 / 3 = 0.6666666666666666`). The Python fallback's own
`math.div` (invocations/math.py) returned a Python `float` for
Integer/Integer division, violating §6.6.2 "The result of a division is
always Decimal, even if the inputs are both Integer" (`1 / 3 = 0.3333333333333333`
evaluated false while displaying exactly that text).

Fix (both engines, this launch): (1) native `evalBinaryOp` routes `+ - * /`
over operands carrying exact decimal digits (Integer, JSON int, plain
source_text) through new exact Decimal string arithmetic
(`tryDecimalArithmeticText` + `FpDecimalDigits` in evaluator.cpp) that
mirrors the Python `decimal` module default context — 28 significant
digits, ROUND_HALF_EVEN, ideal-exponent scale preservation, division via
long division with a 29-digit guard stream + tie-break continuation,
integral quotients quantized to one decimal place, zero products keeping
ideal-exponent scale, and IBM zero-sign rules (left sign for both-zero
adds, positive zero for nonzero cancellation, XOR sign for div/mul).
`decimal_val` is re-anchored via `strtod(source_text)` per the FP-11
pattern so `fhirpath_number` matches `float(Decimal)`. JSON reals and
text-less Decimals still defer to the binary64 path. (2) Python `math.div`
converts Integer operands to Decimal before dividing and guards the
integral `quantize` against `InvalidOperation` (a pre-existing UDF crash
for ≥28-digit quotients such as `9999999999999999999999999999.99999999 / 1`).
No official R4 fixture pins raw division display/equality (only
`(1.2/1.8).round(2)`, tests-fhir-r4.xml:907-908), so §6.6.2 + engine
parity govern the direction; the Python core engine (935/935) defines the
canonical semantics. The FP-18 HISTORIAN float-truediv assumption in the
evaluator comment and the FP-18 division-display test expectations were
corrected. Regression coverage:
`test_arithmetic_parity.py::test_decimal_arithmetic_exact_text_parity_fp01_explorer`,
`test_division_decimal_equality_semantics_parity_fp01_explorer`,
`test_division_no_scientific_notation_in_json_fp01_explorer`, updated
`test_division_uses_shortest_roundtrip_text_fp18_historian`. After native
changes the bundled `fhirpath.duckdb_extension` was rebuilt + redeployed.
Differential validation: 8463-case native-vs-Python-Decimal corpus 0 FAIL.

Exotic-literal surfaces verified clean by the same probe set (221 cases):
leap-second `:60` spellings invalid per the §4.1.6/§4.1.7 value range,
±14:00 offset bounds, >3-digit fractional seconds, midnight-wrapping time
arithmetic, partial-date comparisons, lone-surrogate escapes invalid,
quantity abbreviated-UCUM/fractional/negative spellings.


### FHIRPath FP-04 SKEPTIC §5.2 filtering/projection audit (2026-08-17, spec-compliance campaign)

First personality on §5.2 where/select/repeat/ofType (105 dual-path probe
cases in `/mnt/d/fhir4ds/.temp/qa/fp04_skeptic_2026_08_17/`). where/select/
repeat semantics (strict singleton-boolean criteria, select flattening,
repeat `=`-dedup fixpoint incl. quantity-aware `1 'cm'`/`10 'mm'` → 1) are
parity-correct and spec-correct.

- KNOWN FRAGILE AREA (QA-001, MEDIUM — RESOLVED 2026-08-17): `is`/`as`/
  `ofType` on JSON objects reached through unmodelled fields diverged
  between engines. FIXED: native `structuralFHIRComplexType()` in
  evaluator.cpp now mirrors Python `TypeInfo.create_by_value_in_namespace`
  (nodes.py); the blanket BackboneElement default was replaced by
  structural detection plus a curated known-backbone-field set
  {communication, component, compose, contact, expansion, item, link}
  (from models/r4/fhir_path_to_type.json); `type()` on unknown objects
  now reports FHIR.object. Guard: dual-path parity requires the two
  inference orders to stay in lockstep — update both when the fallback's
  structural heuristics change. Regression:
  `test_structural_complex_type_tests_match_cpp_fp04_skeptic`
  (fhir4ds/fhirpath/duckdb/tests/integration/test_environment_type_parity.py).
- NOT A BUG: `ofType(System.String)`/`is System.String` on FHIR string
  data returning empty/false is spec-correct — the FHIR FHIRPath page
  pins `Patient.name.given.is(System.String).not()` and states
  "FHIR.string is a different type to System.String". Both engines agree.
- NOT A BUG: `id.ofType(FHIR.string)` → empty in both engines; FHIR
  primitives are independent types (markdown is not a subclass of
  string), so exact primitive ofType only matches the declared field type.
- Spec verbatim pin: repeat() dedup uses `=` ("as long as the projection
  yields new items (as determined by the = operator)"); order undefined.

### FHIRPath FP-04 EXPLORER §5.2 audit (2026-08-17, spec-compliance campaign)

Third personality on §5.2 closed the FP-04 chunk: 62 dual-path
evaluations (probe at `/mnt/d/fhir4ds/.temp/qa/fp04_explorer3_probe.py`),
ZERO parity diffs, ZERO spec violations, conformance 2832/2832 held, no
code changes. Final chunk tally: SKEPTIC 1 fix + 1 LOW INTENDED,
HISTORIAN clean, EXPLORER clean.

- NOT A BUG: defineVariable references use the `%name` environment
  variable form (see `test_filter_projection_parity.py`
  `a.where(defineVariable('leak', $this).exists()).select(%leak)`).
  Spec-ballot `$name` identifiers are rejected by the pattern validator on
  both the native and fallback surfaces (consistent INTENDED). `%name`
  evaluates once at its definition context —
  `name.defineVariable('f', family).where(%f = 'Chalmers')` → empty is
  correct because `%f` is the 2-element family collection vs a singleton
  (§6.1 equality).
- NOT A BUG: `%` is not a FHIRPath arithmetic operator (`mod` is).
  Expressions using `%` parse leniently to empty on both engines at the
  UDF boundary (parity holds; the core Python parser rejects them).
- Verified-clean (do not "fix"): repeat() termination on
  self-referential fixpoints — `repeat($this)`, constant projections
  (`id.repeat('x')` → [p1,x]), ping-pong navigation
  (`repeat(given | family | $this.given)`) — all dedup-terminate via the
  `=` operator; cyclic objects cannot cross the JSON SQL UDF boundary, so
  semantic-equality dedup is the sole termination guarantee and it holds.
  ofType unknown type names (`BogusType`, `Collections`) → empty on both
  engines (the Python fallback logs "Unknown type", native is silent —
  parity is defined at the UDF output boundary, not the log).
- Probe-harness doctrine (from this launch's false positives): dual-path
  parity must compare a native-extension connection against a forced
  Python-fallback connection (`duckdb.__version__ =
  "0.0.0-forced-python-fallback"` + `register_fhirpath(con)`), both
  queried through `SELECT fhirpath(?, ?)`. Comparing native UDF output
  (JSON-serialized) against raw `fhir4ds.fhirpath.evaluate()` output
  produces phantom failures (['3'] vs [3], syntax strictness deltas).

### FHIRPath FP-04 HISTORIAN §5.2 audit (2026-08-17, spec-compliance campaign)

Second personality on §5.2 where/select/repeat/ofType (79 fresh dual-path
probe cases in `/mnt/d/fhir4ds/.temp/qa/fp04_historian_2026_08_17/`):
ZERO parity diffs, ZERO new spec violations; no code changes; conformance
2832/2832 held. The SKEPTIC structural-type fix was re-verified
spec-correct and regression-free on 12 edge cases.

- Verified-clean seams worth keeping pinned (do not "fix"): defineVariable
  inside where() criteria does NOT leak into subsequent select() in either
  engine (both error identically on later access); $index is restored after
  where() and correctly scoped in nested select-in-select; `as Quantity`
  inside where() criteria is NOT a boolean predicate (error → empty in
  both, consistent with the strict singleton-Boolean criteria doctrine).
- ofType supertype/profile matrix (both engines agree): DomainResource and
  Resource match resources; Element does NOT match resources (0 — matches
  the R4 model hierarchy where resources are not Elements for ofType
  purposes); subtype/supertype chaining works both directions; Age and
  Duration reject temperature AND energy quantities (FP-15 unit-category
  doctrine extends to ofType); SimpleQuantity → 0 (Quantity is the ofType
  selector per the FHIR FHIRPath page); System.* specifiers never match
  FHIR-typed data (pinned `is(System.String).not()` doctrine extends to
  `ofType(System.Integer)` → 0).
- repeat() confirmed: value-growth fixpoints terminate via `=`-dedup;
  FP-02 derived-unit equality flows through repeat dedup and
  select().distinct() (1 'kJ' vs 1000 'J' collapse); repeat does NOT
  re-navigate projected scalars (`tree.repeat(item.v)` yields the first
  projection's values then stops — the projection is applied to items,
  and integers have no `.item`).
- select() flattens without dedup (`repeat(item).select(v)` keeps all 4);
  where() returns ORIGINAL items (verified via `.code`/`.unit`/
  `.type().name` pins).



Fresh v1.1-campaign audit of §5.1 Existence (141 dual-path probe cases + 25-case
blast-radius battery + 2 focused batteries in
`/mnt/d/fhir4ds/.temp/qa/fp03_skeptic_2026_08_16/`). Verified clean: the full
allTrue/anyTrue/allFalse/anyFalse truth tables incl. non-Boolean error paths
and all four empty-input corners; all/exists criteria singleton doctrine,
vacuous all() on empty input, $index exposure and scope restoration;
subsetOf/supersetOf §5.1.8/§5.1.9 empty-collection corners, root-context
`other` evaluation, `=`-membership incl. 1=1.0 and 'cm'/'mm' quantities;
distinct/isDistinct via `=` (key-order-different JSON objects dedup;
precision-mismatched Dates stay distinct; `(1.0|1).isDistinct()`=true is
CORRECT because `|` union dedups at construction — use `combine` to build
duplicate-bearing collections when testing the §5.1.12 shorthand); count()
(empty→0, Integer, JSON-null array elements skipped); is_valid arity
classification (10 malformed-arity cases invalid on both surfaces).

Two issues filed, BOTH FIXED in iteration 1 (extension rebuilt + redeployed;
conformance 2832/2832 held):
- **QA-001 (HIGH, FIXED): native comparison type-mismatch swallow.**
  `evaluator.cpp` `evalBinaryOp` comparison branch returned `{}` for
  incompatible operand types (the "One numeric, one not" site and the
  incompatible-types catch-all) instead of the §6.2 evaluation error.
  Invisible at UDF top level (wrapper error→NULL) but decisive inside
  `all()`/`exists()`/`where()`/`select()`/`iif()` criteria:
  `mixed.all($this > 0)` → native false (WRONG) vs fallback empty
  (spec-correct). Fixed with `throwIncompatibleComparison()` producing the
  canonical Python-core message form `Type of "X" (T) did not match type of
  "Y" (T). InequalityExpression`, accepted by BOTH is_valid classifiers
  (`udf.py::_is_valid_empty_result_error` and native
  `FhirpathIsValidFunction`). Spec-mandated empty comparison results
  (partial temporal precision, calendar-vs-UCUM, offset temperatures,
  incompatible quantity dimensions) are NOT type errors and stay empty.
  LESSON: an empty-vs-error divergence inside operators is invisible in
  top-level UDF probes (wrapper converts both to NULL) — probe it through
  iteration functions (`all()`, `exists()`, `where()`, `select()`, `iif`)
  where the distinction changes the result.
- **QA-002 (MEDIUM, FIXED): time-string ORDERING coercion in the fallback.**
  The Python `_compare` typecheck coerced time-shaped plain strings against
  `FP_Time` peers (`'10:00' < @T10:30` → true) while native returns empty —
  contradicting the pinned Time-vs-String equality convention
  (String→Time Explicit-only, FP-01 QA-003). `FP_Time` was removed from the
  str→temporal coercion branches in `equality.py`. Date/DateTime-shaped
  string ordering coercion is shared by BOTH engines and is intentional —
  do not "fix" it.
- Regression coverage:
  `test_criteria_comparison_type_error_parity_fp03_skeptic` and
  `test_time_string_ordering_not_coerced_parity_fp03_skeptic` in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_existence_parity.py`.
- Native rebuild targets: `make fhirpath_extension` builds only the static
  lib; `make fhirpath_loadable_extension` (in
  `extensions/fhirpath/build/release`) produces the loadable
  `fhirpath.duckdb_extension` that must be copied to
  `fhir4ds/fhirpath/duckdb/extensions/` and site-packages.

ENVIRONMENT REMINDER (repeat): run dual-path probes with
`PYTHONPATH=/mnt/d/fhir4ds` or imports resolve from stale site-packages.

### FHIRPath FP-03 EXPLORER existence audit (2026-08-17, spec-compliance campaign)

Third personality on §5.1 Existence (150 fresh dual-path probe cases in
`/mnt/d/fhir4ds/.temp/qa/fp03_explorer_2026_08_17/`): ZERO parity diffs,
ZERO new spec violations; no code changes; conformance 2832/2832 held.

- Adversarial chaining battery: §5.1 outputs feeding `not()`, `and`/`or`
  (infix), `convertsToInteger()`, `trace()`, `first()`, `iif()`,
  self-chains (`distinct().distinct()`, `count().count()`,
  `isDistinct().isDistinct()`, `empty().empty()`) — all correct in both
  engines.
- distinct()/isDistinct() on nested lists, identical `contained` resources,
  key-order-different JSON objects, mixed-type collections
  (`1|1.0|'1'|true` → 3 distinct) — deep equality is parity-correct.
- subsetOf/supersetOf with self, partial coverage, boolean/Integer `other`
  arguments (`supersetOf(nums.count())`), quantity literals, and
  derived-unit members (`180 'cm' | 1.8 'm'` → 1 distinct) — all clean.
- count() keeps navigation duplicates (qtys.count()=2 vs distinct=1),
  `|` dedups at construction, combine() correct, JSON-null array elements
  skipped; `{}.count()`=0, `{}.empty()`=true, `{}.isDistinct()`=true.
- Null propagation: `n.empty()` true for null value, `n.empty().empty()`
  false, nulls inside all/exists criteria behave as not-true — uniform.
- NOT A BUG (grammar): dotted `X.and(Y)` / `X.or(Y)` / `X.xor(Y)` are
  INVALID FHIRPath — `and`/`or`/`xor` are reserved infix keyword operators,
  not invocable function names. Both engines return empty + is_valid=False;
  the infix `X and Y` form evaluates correctly. `.not()` IS a function.
- Criteria-singleton convention (shared, coherent with the spec's
  `exists(c) ≡ where(c).exists()` shorthand): non-Boolean multi-item
  criteria (`nums.exists(nums)`) evaluate as not-true → false, never error.

### FHIRPath FP-03 HISTORIAN existence audit (2026-08-17, spec-compliance campaign)

Second personality on §5.1 Existence (141 fresh dual-path probe cases in
`/mnt/d/fhir4ds/.temp/qa/fp03_historian_2026_08_17/`): ZERO parity diffs,
ZERO new spec violations; no code changes; conformance 2832/2832 held.

- Both SKEPTIC fixes re-verified spec-correct and regression-free (8
  neighbor variants of the criteria type-error doctrine and the time-string
  ordering convention).
- Cross-chunk seam verified clean: every equality rule landed by FP-01
  (calendar keywords: `1 month subsetOf (30 days|7 days)` true, `1 year |
  365 days` → 1 distinct, `1 month | 1 'mo'` stays 2 per the fixture-pinned
  empty equality) and FP-02 (derived units `1 'kJ' | 1000 'J'` → 1;
  exponent merge `1 'm2/m' | 1 'm'` → 1; `12 'cm2' / 3 'cm' subsetOf
  4 'cm'` true) flows through subsetOf/supersetOf/distinct/isDistinct
  identically in both engines. §5.1 has no membership code path that
  bypasses the shared `=` helper.
- Equality-EMPTY members behave uniformly as "not a member / still
  distinct" (offset temperatures, incompatible quantity dimensions,
  partial temporal precision) — do not "fix" these to errors.
- `(1 | 1 '1')` dedups via distinct() (Integer = Quantity('1') is true);
  `(1 'cm' | 1)` correctly does NOT (different values).
- Documented shared conventions re-confirmed (do not "fix"): prefix
  `not (...)` inside criteria → empty (unary `not` is not FHIRPath
  grammar; use `.not()`); bare root paths inside criteria resolve against
  `$this`, not the resource root, so `nums.exists($this = nums.count())`
  is false.

### FHIRPath FP-02 SKEPTIC operator audit (2026-08-16, spec-compliance campaign)

Fresh v1.1-campaign audit of §4.2/§4.3/§4.4/§4.5 (163 dual-path probe cases,
spec N1 + official R4 fixture truth tables). Four findings, ALL RESOLVED in
iteration 1 (fixes verified on BOTH the native extension — rebuilt and
redeployed — and Python fallback):

- **QA-003 (HIGH, FIXED): Quantity `*`/`/` result units never merged
  exponents.** `12 'cm2' / 3 'cm'` produced `0.04 'm2/m'` (spec §6.6.2
  example: `4.0 'cm'`) so `= 4 'cm'` was EMPTY; `3 'cm' * 12 'cm2'` produced
  `0.000036 'm.m2'` (spec §6.6.1: `36 'cm3'`); user-authored unreduced
  spellings (`1 'm2/m' = 1 'm'`) were unconvertible; dimensionless squares
  rendered unit `'12'`. Fix: UCUM term-expression exponent algebra in both
  engines — Python `FP_Quantity._parse_unit_exponents` /
  `_render_unit_exponents` / `_unit_reduces_to_base` + `conv_unit_to_base`
  multi-term path + `conv_unit_to` base bridge + merged composition in
  `__mul__`/`__truediv__`/`__rtruediv__`; native
  `fhirpathParseUnitExponents`/`fhirpathRenderUnitExponents`/
  `fhirpathComposeQuantityUnits` + `convertQuantityToBase` fallback.
  RENDERING RULE: sorted base symbols so Python and C++ emit byte-identical
  spellings; existing single-unit forms ('m2', '1/mg', '1/s', 'g/s', 'g.m')
  are unchanged. `1 'm2/cm2' = 10000` (dimensionless reduction) now works.
- **QA-001 (MEDIUM, FIXED): fallback `fhirpath_is_valid_udf` violated §6.8
  precedence.** `_has_invalid_math_literal_operands` (udf.py) treated the
  full textual side of a top-level math operator as its operand, so valid
  `arith | union` mixes (`1 + 2 | 3` → {3}, `1 | 2 + 3`, `'a' | 'b' & 'c'`)
  returned is_valid=False while the extension returned True. Fix:
  `_split_top_level_pipe_segments` splits top-level `|` first and recurses
  per segment; parenthesized multi-item operands (`(1 | 2) + 3`) still
  invalid.
- **QA-004 (MEDIUM, FIXED; found during fix verification): quantity ORDERING
  used a narrower conversion surface than EQUALITY.** `1 'mm[Hg]' < 200
  'Pa'` was true natively but empty in the Python fallback because
  `FP_Quantity.compare()` only consulted `conv_unit_to`'s special groups,
  while equality used `conv_unit_to_base` (so `=` and `~` already worked).
  Fix: `compare()` falls back to base-table comparison; offset temperatures
  (Cel vs K), unknown units, and calendar-vs-UCUM pairs remain empty.
- **QA-002 (LOW, FIXED): unary `+`/`-` on non-numeric literals was
  classified syntactically invalid in both backends while equivalent binary
  type errors (`'a' - 'b'`) were valid.** `_is_valid_empty_result_error`
  (udf.py) and native `FhirpathIsValidFunction` now accept the unary
  non-numeric execution-type errors per the is_valid doctrine
  (GLOBAL_RULES). Singleton violations ("requires a single item") stay
  invalid. The stale FP-06 pin `-1.convertsToInteger()` → is_valid=False
  was updated to True: official fixtures mark BOTH unary testPrecedence1 and
  binary testMinus4 `invalid="execution"`, the strict core still errors, and
  the DuckDB validity helper is documented to accept execution type errors.

Verified clean (negative results worth keeping): full and/or/xor/implies
three-valued truth tables incl. all empty corners; div/mod truncation for
negative integers AND decimals; comparison type errors → empty; spec §6
preamble `{} = {}`/`{} != 'dummy'`/`true > {}` → empty; §4.3 constants→
collections; §4.4 empty propagation incl. union-with-empty; §4.5 multi-item
error paths; §6.8 precedence corners incl. `-3.abs()` vs `(-3).abs()` and
`true or false implies false`; ordered `=` vs unordered `~` multi-item
semantics. INTENDED: `1 & 2` → '12' (reference coerces singletons via
toString — pinned by fixture testConcatenate4 expected text '1,2,3b');
integer overflow promotes to Decimal (`2147483647 + 1` → `2147483648.0`);
`substring(1, {})` ignores empty length per §5.5.2/§5.6.2 override of
§4.4.1.

### FHIRPath FP-02 HISTORIAN operator audit (2026-08-16, spec-compliance campaign)

Fresh HISTORIAN audit of §4.2–§4.5 (158 dual-path probe cases grounded in the
N1 normative HTML fetched from hl7.org/fhirpath/N1 — separating N1-pinned
examples from continuous/STU-only text — plus official R4 fixture checks).
All 4 FP-02 SKEPTIC fixes re-verified intact and regression-free. Four new
MEDIUM findings, ALL RESOLVED in iteration 1 (both engines; extension rebuilt
and redeployed):

- **QA-001 (parity): native `+`/`-` missed the Integer/Decimal→Quantity('1')
  implicit conversion.** `2 + 2 '1'` → native empty vs fallback `4 '1'` (while
  `2 * 2 '1'` worked natively). Fix: evaluator.cpp wraps the numeric operand
  via the existing `numericValueAsUnitQuantity()` before the Quantity±Quantity
  block; math.py's four wrap sites unified to the canonical quoted unit
  `"'1'"` (the unquoted form rendered `4 1`).
- **QA-002 (N1 §6.6.1/§6.6.2/§6.6.3): quantity arithmetic composed in
  BASE-unit space.** `12 'cm' * 3 'cm'` → `0.0036 'm2'` vs N1 `36 'cm2'`;
  `12 'cm2' / 3 'cm'` → `0.04 'm'` (spec: `4.0 'cm'`); `3 'm' + 3 'cm'` →
  `3.03 'm'` (spec: `303 'cm'`). Fix: compose in OPERAND unit space — merge
  raw operand term-exponents, operate on operand values; mixed prefixes keep
  the ratio in the unit (`0.1 'cm/mm'` with `= 1` still true via base
  reduction; fixture testQuantity9 unaffected). Addition renders in the
  most-granular operand unit (smaller base factor; ties prefer the canonical
  operand so `1 'm2/m' + 1 'm'` stays `2 'm'`). Bonus: calendar additions now
  match the continuous build verbatim (`1 'wk' + 2 days // 9 days`).
  GOTCHA: `fhir4ds/fhirpath/engine/invocations/math.py` defines the FHIRPath
  `abs` function — the builtin `abs` is shadowed module-wide; use an inline
  magnitude helper there.
- **QA-003 (N1 §6.2): calendar week/day/time keyword vs UCUM ORDERING was
  empty while equality worked** (`1 day = 24 'h'` true but `1 day > 23 'h'`
  empty; `1 month > 29 'd'` true but `1 week > 6 'd'` empty) — the 4th
  instance of the equality/ordering conversion-surface family. Fix: both
  guards (`FP_Quantity.compare()` / `isMixedCalendarUcumDurationAboveSeconds`)
  exempt any pair inside the week/day/time set (exact seconds); year/month
  keyword-vs-'a'/'mo' pairs stay empty (fixture-pinned). `1 week > 1 'wk'` →
  false (equal), consistent with fixture testQuantity6 `7 days = 1 'wk'` true.
- **QA-004 (N1 §6.1.1): derived UCUM units were absent from the conversion
  tables** (`1 'kJ' = 1000 'J'`, `1 'J' = 1 'kg.m2/s2'`, `1 'N.m' = 1 'J'`
  all empty). Fix: curated J/kJ, N/kN, W/kW/mW, A/mA, V/kV/mV entries in
  nodes.py plus a FHIRPath-LOCAL `FhirpathDerivedUnitTable()` in evaluator.cpp
  (shared ucum_units.hpp untouched, CQL extension not rebuilt), and the
  multi-term reduction now expands term bases recursively. Base-form
  spellings MUST match the sorted renderer ('g.m2/s2', 'g.m2/A.s3' — V has A
  in the DENOMINATOR). Known remaining gap: Pa stays its own base dimension
  (shared-table constraint), so `1 'Pa' * 1 'm2' = 1 'N'` remains empty until
  both extensions are rebuilt together.

§4.5 singleton-evaluation branch question RESOLVED as INTENDED (spec iif
examples `iif(1/0/'hi', ...)` → then-branch; conversion table makes
Integer/String→Boolean EXPLICIT so branch 2 "single node → true" always
applies). Verified clean: is/as walk (System.* specifiers, temporal literals,
`as` type-assertion no-conversion), `nums = 1` → false (§6.1.1 count
mismatch), `23 = 23 '1'` → true, continuous-build-only divergences documented
(`12 day * 45 'm'` → `540 'day.m'` N1-defensible; `1 year + 12 'mo'` →
`24 'mo'` vs continuous empty; `60 / 1 's'` renders '1/s' vs continuous '/s').

**ENVIRONMENT TRAP:** running probes as `python3 .temp/qa/<dir>/probe.py`
resolves `import fhir4ds` from the STALE site-packages copy (script dir is
sys.path[0], not the cwd) while the native extension there is current —
producing phantom "fallback lost the fix" parity failures. Always run
dual-path probes with `PYTHONPATH=/mnt/d/fhir4ds`.

### FHIRPath FP-02 EXPLORER operator audit (2026-08-16, spec-compliance campaign)

Third personality on §4.2–§4.5 (236 dual-path probe cases + drill matrices).
Verified clean: full §6.8 precedence corners incl. unary polarity tighter than
`* / div mod + -` but looser than `.` (so `-2 + 3`=1, `2 * -3`=-6,
`-3.abs()`=-3) and implies LEFT-associativity (`{} implies false implies {}`
-> empty); all 9 implies corners with missing-field/JSON-null empties (incl.
`{} implies true`=true, `false implies {}`=true); and/or/xor fixture truth
tables incl. `{} and false`=false; `{}`-only collection literal grammar
(multi-element `{1,2}` is NOT FHIRPath syntax — `|` is the constructor; both
engines correctly reject it); union dedup vs `combine` duplicate preservation;
`&` empty-to-empty-string coercion; `{}.iif(true,'a','b')`='a' (fixture
testIif7 — iif on empty focus evaluates); `t is Boolean`=false while
`t is FHIR.boolean`/`t.is(boolean)`=true (fixtures testType11-14 pin the
FHIR-vs-System namespace split — do not "fix" this); `1 / 0`, `1 div 0`,
`1 mod 0` -> empty (fixtures Div5/Mod5). Three issues filed (see
`spec_comp/FP-02/` handoffs): QA-001 fallback registry implements non-N1
`sum`/`min`/`max`/`avg` (native -> unknown/empty; `{}.sum()`->0 even violates
the empty-input convention); QA-002 native `fn_isType` lexical shape-sniffing
for date/dateTime on model-unknown string fields vs fallback model-driven
typing, plus R4 temporal-field metadata gaps on both surfaces
(`MedicationRequest.authoredOn` is dateTime — fallback said false; native
table types `Observation.issued` dateTime but R4 says instant); QA-003
boolean-vs-boolean ordering (`true > false`) classified is_valid=False while
mixed-type ordering errors are True.

**FP-02 EXPLORER fixes (same launch, all three RESOLVED; extension rebuilt +
redeployed):** QA-001 removed `sum`/`min`/`max`/`avg` from the Python engine
invocation registry (NOT N1/R4 functions — the fallback was evaluating
expressences its own is_valid rejects; `{}.sum()` had returned 0). The public
direct helpers in `duckdb/functions/math.py` are a separate module and remain.
QA-002: `fn_isType` lexical date/dateTime shape-sniffing branches were REMOVED
(`is` operates on the operand's type — model-unknown date-shaped string fields
are FHIR.string on both surfaces, consistent with `type().name`); `instant` and
`dateTime` are SIBLING R4 primitives (canonical `models/r4/type2Parent.json`:
instant→Element; the stale instant→dateTime edge was fixed in BOTH the native
`fhirTypeIsA` and `duckdb/fhir_types_generated.py`); native `fhirFieldType`
now maps `issued`→instant (R4) and `authoredOn`→dateTime; native
`infer_fhir_type` suffix list gained "Instant"; `models/r4/fhir_path_to_type.json`
gained `.issued`→instant, `.authoredOn`→dateTime, `.date`→dateTime. Keep the
native `fhirFieldType` table and the Python `fhir_path_to_type.json` aligned
when adding fields; full R4 temporal coverage (e.g. DocumentReference.date is
instant while Composition.date is dateTime — name-only metadata cannot express
this) needs resource-qualified metadata (see generated `path2Type.json`,
7,705 entries). QA-003: the "Comparison operators are not defined for Boolean
operands" execution-type error is now accepted by `fhirpath_is_valid` on both
surfaces (same class as `1 > true`). KNOWN DEFERRED (QA-004, LOW): unknown-
function chaining diverges pre-existingly — native continues the chain with
empty (`{}.foo().empty()` → true) while the fallback errors the whole
expression (→ empty); the native convention is documented load-bearing for
ViewDef; only affects is_valid=False expressions.

### FHIRPath §6.4 Collections: |, in, contains

**Verified CLEAN in FP-16 SKEPTIC iter 1 (2026-06-29).** A 148-case
hypothesis-driven probe across 5 rounds (53 + 29 is_valid + 37 + 29 cases)
targeting all 8 orchestrator-briefed §6.4 bug classes produced 0 new
non-terminal CRITICAL/HIGH/MEDIUM issues. The §6.4 surface is well-
hardened across native C++ and Python fallback paths. Coverage:
empty handling (10 cases), multi-item needle (4 cases), mixed-type
membership (9 cases), Quantity cross-unit membership (7 cases incl.
FP-13 HISTORIAN offset-temperature carry-over re-verified:
`0 'Cel' in (32 '[degF]' | 100 '[degF]')` → false in both backends
because equality returns empty per the offset-temperature guard, and
"empty equality" means "not a member" per §6.4.2 definition),
Date/DateTime/Time precision-aware membership (4 cases), ResourceNode
unwrap (5 cases), union dedup semantic equality (10 cases — `(1 | 1.0).count() = 1`,
`(1 'g' | 1000 'mg').count() = 1`, `({} | 1).count() = 1`), union
order unspecified but dedup correct (4 cases), plus 37 pathological
stress cases (Unicode/emoji, 1000-item collections, polymorphic
choice-types, nested unions, iif needles, resource-typed collections)
and 29 final edge cases (Decimal precision 1.0 vs 1.00000, singleton
Date/Time equality with Z/no-tz variants, composed where() filters,
negation interaction, subtree identity). The `fhirpath_is_valid`
precheck `_has_invalid_membership_literal_unions` (udf.py:929-950)
correctly detects statically-known multi-item needles
(`(1 | 2) in ...` → `is_valid=false`) in 29/29 cases. All 8
pre-test SKEPTIC hypotheses (H1-H8) empirically REJECTED.
Implementation cross-check: Python `fhir4ds/fhirpath/engine/invocations/
collections.py:336-367` (`contains_impl`/`contains`/`inn`) and
`combining.py:9-10` (`union_op`); native `extensions/fhirpath/src/
fhirpath/evaluator.cpp:7305-7332` (`in`/`contains` in `evalBinaryOp`)
and `6521-6540` (`fn_union`). Both backends correctly implement
spec-mandated empty-collection semantics, multi-item needle rejection,
and equality-based dedup/membership. No source changes, no new
regression tests (surface already spec-compliant), no native C++
rebuild. Full conformance 2822/2822 unchanged. Probes:
`/mnt/d/fhir4ds/.temp/qa/fp16_skeptic_2026_06_29/probe{,2,3,4,5}.py`.

### FHIRPath Subsetting Integer Arguments and `intersect()` Equality

**Fixed in FP-05 SKEPTIC subsetting/combining audit (2026-05-16).** The indexer, `skip(num)`, and `take(num)` require Integer arguments; do not coerce strings, booleans, decimals, or JSON numeric reals through `int()`/`toNumber()`. Public DuckDB wrappers convert those type errors to empty/NULL instead of selecting data. `intersect(other)` must use FHIRPath `=` equality, matching `union()`/`distinct()`, so compatible quantities such as `1 'cm'` and `10 'mm'` intersect as one value. After C++ subsetting changes, rebuild and copy the bundled `fhirpath.duckdb_extension`.

**FP-05 spec-compliance SKEPTIC fresh rerun (2026-08-17): §5.3/§5.4 evaluation
clean; is_valid classification fixed.** A fresh N1-grounded dual-path audit
(120 probe cases) confirmed all §5.3/§5.4 semantics correct in both engines
(indexer out-of-range/negative/empty → empty; `single()` 0→empty, 2+→error per
N1; `skip(num<=0)` returns the input; `take(num<=0)` empty; intersect dedups
via `=` while exclude/combine keep duplicates — probe duplicate-preservation
only with `combine`-built collections since `|` dedups at construction). One
MEDIUM fix: `fhirpath_is_valid` reported False for statically-known
wrong-typed §5.3 arguments (`skip('x')`, `take(true)`, `[1.5]`, `'abc'['x']`)
on BOTH surfaces, inconsistent with the accepted execution-type-error doctrine
(`'a' - 'b'` → True). Both message-coupled classifiers were updated in
lockstep (`udf.py::_is_valid_empty_result_error` + native
`FhirpathIsValidFunction`); singleton/multi-item variants stay invalid.
Guard test:
`test_subsetting_argument_type_error_validity_classification_fp05_skeptic`
in `test_operator_parity.py`. PROBE TRAP (3rd instance): a "native" probe
connection without `config={'allow_unsigned_extensions': True}` silently
registers Python UDFs — always assert `register_fhirpath(con) is True`.

**FP-05 spec-compliance HISTORIAN confirmation (2026-08-17): clean.** 82 fresh
dual-path evaluations + 24 is_valid checks, zero parity diffs, zero new
violations; the is_valid fix above was re-verified including over-acceptance
risk (temporal wrong-type args `skip(@2020-01-01)` also True; singleton/multi
and grammar-invalid forms still False on both surfaces). Doctrine pins: strings
are singletons, not char collections (`'abc'[1]`/`'abc'.skip(1)` → empty);
Integer-valued Decimals stay Decimals (`skip(1.0)` → execution type error →
empty); FP-02 derived-unit equality flows through every §5.4 combiner;
`{}.single()` is empty-not-error so it acts as the empty-operand corner inside
union/exclude/intersect/combine arguments. PROBE TRAP (4th instance): probe
helper TypeErrors (e.g. `json.loads` on an already-list fetchone result)
masquerade as engine exceptions — re-verify flagged cases with a direct
`SELECT fhirpath(?, ?)` before logging an issue.

**FP-05 spec-compliance EXPLORER confirmation (2026-08-17): clean; chunk
closed.** Third personality on §5.3/§5.4 (144 fresh dual-path adversarial
chaining cases in `/mnt/d/fhir4ds/.temp/qa/fp05_explorer_2026_08_17/`):
zero parity diffs, zero spec violations; conformance 2832/2832 held; no
code changes. Doctrine pin (do not "fix"): `tail()` is ZERO-ARG (§5.3.4,
"equivalent to skip(1)") — `tail(n)` is wrong ARITY and correctly yields
is_valid=False + empty on BOTH surfaces; this is distinct from wrong-TYPE
arguments (`skip('x')`, `a[1.0]`), which are valid execution-type errors
per the FP-05 SKEPTIC doctrine. Verified-clean seams: chained subsetting
(skip/take/tail composition, computed/negative indexers, 1e9 numerics,
200-element collections), combiners ∘ repeat() fixpoints, combine-vs-
select flattening depth, mixed-resource exclude/intersect via ofType,
odd-precision temporal/quantity equality through every combiner (partial
Dates distinct; cm/mm, kJ/J, 1 vs 1.0 collapse per `=`), self-referential
and root-context `other` operands. Lesson: when an entire function family
appears broken in a probe, verify the probe's arity assumptions against
the spec grammar before filing.

### FHIRPath Expression-Parameter Scope Restoration

**Fixed in milestone review-5 remediation (2026-05-16).** Every expression-parameter function must restore transient scope after evaluating criteria/projection expressions. Python `all(criteria)` must save and restore `$index`, matching `where()`/`select()`/`repeat()`. Native C++ `where(criteria)` must save and restore `defined_variables_` in addition to `chain_defined_vars_` and `index_context_`; `defineVariable()` inside criteria must not leak into subsequent chained expressions. Regression coverage lives in `test_existence_parity.py` and `test_filter_projection_parity.py`.

### FHIRPath Tree Navigation Nulls and Trace Projection

**Fixed in FP-12 SKEPTIC tree/utility audit (2026-05-17).** `children()` and `descendants()` expose child nodes, including JSON null-valued children; ordinary field navigation may still skip nulls. Native UDF result materialization must preserve nulls with an owned sentinel after `yyjson_doc_free()` so `fhirpath_json(..., 'children()')` can emit JSON `null` and `count()` sees the child-node item. `trace(name, projection)` must return the original input unchanged while logging the projection result, with `$this` restored after projection evaluation. Regression coverage lives in `test_tree_utility_parity.py`, `test_new_functions.py`, and `extensions/fhirpath/test/sql/fhirpath.test`; after native changes, rebuild and copy the bundled `fhirpath.duckdb_extension`.

### FHIRPath Current-Time Function Determinism

**Fixed in FP-12 EXPLORER utility audit (2026-05-16).** FHIRPath §5.9.2 requires `now()`, `today()`, and `timeOfDay()` to return the same value regardless of how many times they are evaluated within one expression. Native C++ must cache one timestamp per `Evaluator::evaluate()` call; do not call `time(nullptr)` separately in each function branch. Long expressions can otherwise cross a second boundary and make `now() = now()` false. Regression coverage lives in `fhir4ds/fhirpath/duckdb/tests/integration/test_tree_utility_parity.py`; after native changes, rebuild and copy the bundled `fhirpath.duckdb_extension`.

### FHIRPath Conversion Singleton and Type Tables

**Fixed in FP-06 SKEPTIC conversion audit (2026-05-16), tightened in review-10 remediation (2026-05-17).** Integer conversion is not decimal truncation: `toInteger()` and `convertsToInteger()` accept Integer, Boolean, and strings matching `(+|-)?\d+`, but Decimal inputs such as `1.0` must return empty/false. Do not validate integer strings with APIs that skip whitespace, such as `std::stoll`, unless an exact regex-style guard runs first. Conversion-section functions, including `iif()`, must enforce singleton input before evaluating arguments; DuckDB public wrappers should convert these semantic errors to empty/NULL outside strict mode. Direct helper APIs in `fhir4ds/fhirpath/duckdb/functions/conversion.py` must use the same Boolean, Date, Time, DateTime, and Quantity conversion tables as the public/core path; do not strip whitespace, truncate malformed DateTime strings, accept timezone-bearing Time strings, or ignore incompatible target units. Regression coverage lives in `test_conversion_parity.py`, `test_operator_parity.py`, and `test_conversion.py`; after native changes, rebuild and copy the bundled `fhirpath.duckdb_extension`.

### FP-06 spec-compliance SKEPTIC rerun doctrine pins (2026-08-17)

Fresh §5.5.1–§5.5.3 dual-path audit (209 cases, probe
`/mnt/d/fhir4ds/.temp/qa/fp06_skeptic_2026_08_17/`): zero parity diffs, zero
spec violations, conformance 2832/2832, no code changes. Two NOT A BUG pins:

- `convertsToInteger('2147483648')` → **false** in BOTH engines (QA-001, LOW
  INTENDED): a string outside the 32-bit Integer range is not convertible —
  Integer-range semantics govern over the prose-literal `(\+|-)?\d+`-only
  reading, consistent with `toInteger` returning empty for the same input. No
  official fixture pins overflow strings. Do not "fix" to regex-only true.
- `iif('non boolean criteria', ...)` → execution error in the strict core
  (fixture testIif6 `invalid="execution"`), and non-Boolean singleton criteria
  follow the §4.5 singleton doctrine at the DuckDB wrapper boundary (QA-002,
  LOW INTENDED; re-confirms the FP-02 HISTORIAN strict-mode branching doctrine).
  Verified: `iif` is lazy in both engines (`iif(false,1/0,'safe')` → 'safe',
  `iif(true,'safe',1/0)` → 'safe').

### FP-06 HISTORIAN rerun fixes (2026-08-17)

Second personality on §5.5.1–§5.5.3 (123 fresh dual-path cases, probe
`/mnt/d/fhir4ds/.temp/qa/fp06_historian_2026_08_17/`): three fallback-only
parity fixes, all Python-side (native already correct; extension NOT rebuilt).

- **Python `re` `$` end-anchor matches before a single trailing newline**
  (QA-001/QA-004, MEDIUM ×2, FIXED): `intRegex` and `numRegex` in
  `fhir4ds/fhirpath/engine/invocations/misc.py` used `^[...]+$`, so
  `'1\n'.toInteger()` → `1` and `'1\n'.toDecimal()` → `1.0` in the fallback
  while native correctly returns empty (exact `(\+|-)?\d+` grammar, §5.5.3/
  §5.5.4). Both now anchor with `\Z`. Same lesson family as the FP-07
  Unicode-`\d` trap: when auditing a lexical regex, check BOTH digit-class
  semantics AND end-anchor semantics. `longDecimalStringRegex` still ends in
  `$`; its public surface (`toLong`) is not registered in this build — the
  FP-07/Long chunk owner should pre-harden it to `\Z`.
- **Fallback `iif_macro` leaked defineVariable out of branches** (QA-002,
  MEDIUM, FIXED): `iif(true, defineVariable('dv', 9).select(1), 2).select(%dv)`
  → `9` in the fallback vs empty natively. `iif_macro` now saves/restores
  `ctx['vars']` around the criterion and both branches and evaluates each
  branch with a cleared `_chain_defined_vars_`, mirroring native `fn_iif`
  (`evaluator.cpp:7169`). Variables remain visible inside their defining
  branch; variables defined before the iif remain visible in criterion and
  branches.
- Doctrine pin (QA-003, LOW INTENDED): out-of-32-bit-range Integer literals
  (e.g. `99999999999999999999`) evaluate to empty + `is_valid=false`
  identically in both engines — invalid-expression doctrine, do not "fix".
- Verified-clean fresh seams: Unicode digits (Arabic-Indic/fullwidth/Roman)
  rejected by both engines' toInteger/convertsToInteger/toBoolean; exact
  Decimal division seam (`(2/2).convertsToInteger()` → false: Decimal, not
  Integer — FP-01 fix interplay); temporal/object/Quantity inputs →
  empty/false uniformly; iif criteria riding FP-01/FP-02 equality fixes
  (`1 month = 30 days`, `1 'kJ' = 1000 'J'`, `1 'm2/m' = 1 'm'`) agree in
  both engines; laziness with taken-branch error propagation and dead-branch
  suppression (arithmetic and singleton errors).
- Regression:
  `test_conversion_parity.py::test_integer_conversion_trailing_newline_and_iif_scope_parity_fp06_historian`
  (17 cases, native vs forced fallback).

### FP-06 EXPLORER rerun fix (2026-08-17)

Third personality on §5.5.1–§5.5.3 (100 dual-path adversarial chaining
cases, probe `/mnt/d/fhir4ds/.temp/qa/fp06_explorer3_2026_08_17/`):

- **Fallback `iif_macro` hid criterion-defined defineVariable variables
  (QA-001, MEDIUM, FIXED)**: the FP-06 HISTORIAN fix snapshot/restored
  `ctx['vars']` around the criterion, so
  `iif(defineVariable('dc',1).select(true), %dc, 0)` → empty in the
  fallback vs `1` natively. Native `fn_iif` (evaluator.cpp:7169) evaluates
  the criterion in the expression's MAIN scope: criterion-defined variables
  persist for the remainder of the whole expression (true/false/empty
  criteria alike) while branch-defined variables stay branch-scoped — per
  §5.2.9 "available for the remainder of the expression". `iif_macro`
  now follows the same contract; Python-only, no extension rebuild.
  Regression: cases appended to
  `test_conversion_parity.py::test_integer_conversion_trailing_newline_and_iif_scope_parity_fp06_historian`.
- **JSON-`null` root resource parity (QA-002, LOW, DEFERRED)**: Python core
  `util.arraify(None)` → empty collection vs native singleton-null root —
  observable only when a root-chained function's implicit focus is the
  resource (`fhirpath('null', "defineVariable('x',1).select(%x)")` →
  native `['1']`, fallback `[]`). Spec silent, no fixture pins it; mapping
  null→`{}` in the wrapper fixes 8/9 probes but `type().name` still
  diverges (`''` vs `'Object'`). Needs a root-context null-semantics
  decision; do not paper over with a partial wrapper mapping.
- Verified clean: conversions inside `$this`/`$index` iteration,
  iif-in-repeat fixpoints, Quantity conversions, `toBoolean` of
  `'tRuE'`/`'1'`/`'yes'` (N1 possible-representations table;
  `1.convertsToBoolean()`→true fixture-pinned), Unicode digit rejection,
  multi-item criterion errors, conversion-fed arithmetic chains.

### FP-07 spec-compliance SKEPTIC audit (2026-08-17): §5.5.4/§5.5.5/§5.5.6

Fresh dual-path audit of Date/DateTime/Decimal conversion (129 cases, probe
`/mnt/d/fhir4ds/.temp/qa/fp07_skeptic_2026_08_17/probe.py`, live N1 spec +
official R4 fixtures). One fix (QA-003, MEDIUM): the third `$`-anchor
sibling `longDecimalStringRegex` (misc.py) matched `'5L\n'`, and the
fallback `to_decimal` then raised an unhandled `decimal.ConversionSyntax`
UDF crash on `Decimal('5L')` while native returned empty — exactly the
trap FP-06 HISTORIAN flagged for the FP-07/Long owner. Now `\Z`-anchored;
regression cases appended to
`test_conversion_parity.py::test_integer_conversion_trailing_newline_and_iif_scope_parity_fp06_historian`;
conformance 2832/2832 held. Everything else ZERO parity diffs / zero
violations. Verified clean (do not "fix"): Date→DateTime precision
preservation (`@2015.toDateTime()` → `2015T`, `@2015-02T`, `@2015-02-04T`;
time components empty — comparison vs `@2015-02-04T00` stays empty);
DateTime→Date truncation incl. partial precisions and timezone drop;
toDateTime string grammar strictness (lowercase `t`, space separator,
single-digit month, `+99:00`, colonless `+1099` rejected; `Z`, `±hh:mm`,
>3-digit fractional seconds accepted — identically in both engines);
toDecimal exact Decimal text preserved in BOTH engines at 30+ significant
digits (native keeps full `source_text` past binary64; the FP-06 `\Z`
numRegex fix re-verified: `'1\n'` rejected); `'+5'`→`5.0`, `'00'`→`0.0`,
`-0.0`, `1e3`/`'5.'`/`'.5'`/`NaN`/Unicode digits rejected; Quantity→Decimal
empty/false (§5.5 conversion table defines no Quantity→Decimal);
Boolean→`1.0`/`0.0`; multi-item error → empty; empty input → empty. Three
shared-convention pins (LOW INTENDED, both engines agree, no fixture pins):
- `'2015-02-04T14:34'.toDate()` → `2015-02-04` (strict prose reading would
  return empty for dateTime-shaped strings; same function explicitly
  converts DateTime items, so the lenient reading is defensible).
- `'5L'.toDecimal()` → `5.0` (Long-literal suffix interop convention,
  `longDecimalStringRegex`/`isFHIRPathLongDecimalString`; `'5.5L'` rejected
  in both).
- 1-arg `toDate(s)`/`toDateTime(s)`/`convertsToDate(s)` treat the argument
  as a FORMAT string, not the input value (`convertsToDate('2015')` →
  false: the resource input is evaluated against format '2015');
  `convertsToDecimal` has no 1-arg arity (error → empty, is_valid=False).

### FP-07 HISTORIAN confirmation (2026-08-17): §5.5.4–§5.5.6 clean; chunk closed

Second personality on Date/DateTime/Decimal conversion (107 fresh dual-path
cases, probe `/mnt/d/fhir4ds/.temp/qa/fp07_historian_2026_08_17/probe.py`):
zero parity diffs, zero spec violations, conformance 2832/2832 held, no code
changes. The SKEPTIC `longDecimalStringRegex` `\Z` fix re-verified
regression-free (`'5L\n'` → empty both engines; `'-5L'`/`'+5L'` ok;
`'5.5L'`/`'5l'`/`'5LL'` rejected identically). Newly verified-clean seams (do
not "fix"): resource-field-driven conversion on model-typed JSON fields
(`birthDate.toDate()/.toDateTime()`; instant `issued.toDateTime()` keeps
`.123+10:00`; partial `effectiveDateTime: "2015"` → `2015T`); JSON
real/integer/boolean primitives through toDecimal with exact text
(`valueDecimal: 0.1`); calendar-range rejection (non-leap `2015-02-29` vs
leap `2016`/`2000` vs `1900`; `0000`; 5-digit years; Apr 31; hour 24;
minute/second 60; leap-second `:60` spellings; offset `+14:01` vs `+14:00`;
offset-seconds form rejected); whitespace/CR/tab/Unicode-digit rejection
identical in both engines (`'-0'` → `-0.0` parity); conversions chained
through `where()`/`select()`/`iif()`, `toDate().toDateTime()` roundtrip →
`2015-02-04T`, and toDecimal-fed arithmetic; is_valid classification
consistent for wrong-type fmt args and arity forms.

### FP-07 EXPLORER fix (2026-08-17): fallback temporal arithmetic must
### preserve authored `Z`

Third personality on §5.5.4–§5.5.6 (123 fresh dual-path cases, probe
`/mnt/d/fhir4ds/.temp/qa/fp07_explorer3_2026_08_17/probe{,2}.py`): converted
temporals as ± operands (both orders), convertsTo* feeding iif/where/select,
roundtrip precision/offset losslessness, toDecimal at the 28-sig-digit
ROUND_HALF_EVEN boundary × FP-01 exact arithmetic (all clean —
`'0.1'.toDecimal() + 0.2 = 0.3` true; `'2.0'.toDecimal() / 3` exact
28-digit text both engines), extension-value/contained/nested-path
conversions, multi-item collections, converted-value equality/ordering, and
is_valid parity. One fix (QA-001, MEDIUM): `FP_DateTime.
_extractDateByPrecision` (engine/nodes.py) explicitly normalized authored
`Z` → `+00:00` when rendering temporal ARITHMETIC results
(`@2020-06-30T23:59:59Z + 1 second` → fallback `...+00:00` vs native
`...Z`); the timezone suffix is now appended verbatim. Authored `+hh:mm`
spelling, plain conversion, and equality were already correct in both
engines; no fixture pins Z-suffixed arithmetic output, so parity governs.
Regression:
`test_conversion_parity.py::test_temporal_arithmetic_preserves_authored_z_suffix_parity_fp07_explorer`.
NOT A BUG pins (do not "fix"): `2 days + date` operand order → empty both
engines; `'2015-02' + 4 days` → month-precision truncation (§6.7 doctrine);
Decimal↔Quantity ordering empty while equality true; precision-mismatched
converted-DateTime equality empty. Conformance 2832/2832 held.

### FHIRPath Direct String Helper Semantics

**Fixed in FP-09 HISTORIAN string-search audit (2026-05-16).** Public DuckDB UDFs and the core Python fallback agree for §5.6.1-§5.6.5, and direct helper functions in `fhir4ds/fhirpath/duckdb/functions/string.py` must also preserve FHIRPath singleton String semantics. Do not coerce non-string helper input with `str(value)`, and keep `substring(start == length)` empty per the normative example `'abcdefg'.substring(7, 1) // { }`.

**FP-09 spec-compliance SKEPTIC audit (2026-08-17): §5.6.1-§5.6.5 clean;
index_of helper added.** Fresh dual-path audit (164 UDF checks incl. 18
is_valid forms + direct-helper probe, live N1 §5.6 text): zero parity
diffs, zero spec violations across indexOf/substring/startsWith/endsWith/
contains — case sensitivity, first-occurrence/-1/''→0 indexOf semantics,
substring bounds (start≥len → {}, length overrun → remaining, empty
length {} ignored), emptiness rules, non-String/multi-item error paths,
UTF-8 code-point positions (Latin-1/Greek/CJK/emoji) in BOTH engines, and
the contains-function vs contains-operator grammar distinction
(`.contains(` on a multi-item input is the §5.6.5 function → error →
empty, not the §6.4.3 list operator). One fix: `index_of` was missing
from the direct-helper module while all four siblings existed (3rd
instance of the "engine path audited, exported helper API forgotten"
family) — added with §5.6.1 semantics + `STRING_FUNCTIONS` registration
(`TestIndexOfFp09Skeptic` in `tests/unit/test_string.py`). Shared
convention pins (do not "fix"): `''.substring(0)` → `{}` (start==length
boundary treated as outside; spec ambiguous, no fixture) and negative
start → `{}` (consistent with the CQL-12 Substring invalid-boundary
doctrine). CORRECTION (HISTORIAN rerun, same date): the negative pin
splits by argument — negative START → `{}` in both engines, but negative
or zero LENGTH → the empty STRING `''` in both engines (native
`fn_substring` len<=0 → `{""}`; core `strings.substring` length<=0 →
`""`). Do not conflate them.

**FP-09 spec-compliance HISTORIAN audit (2026-08-17): §5.6.1-§5.6.5
engines clean; direct-helper engine-contract gaps fixed.** Fresh
dual-path probe (`.temp/qa/fp09_historian2_2026_08_17/probe.py`, ~60
checks): zero native-vs-fallback parity diffs across new angles —
sourced-call argument focus (native outer-input evaluation vs fallback
agree for `s.indexOf(field)`, `$this` args, sibling-field args), astral-
plane code points (U+1D400 substring/indexOf/endsWith, 4-byte pairs),
combining sequences, length overrun clamping (byte/code-point boundary),
substring length sign matrix, and 7 is_valid classifications. The FP-09
SKEPTIC `index_of` fix was re-verified (helper + registry + engine
parity). One fix (QA-001, MEDIUM, 4th instance of the "exported helper
API forgotten" family): `fhir4ds/fhirpath/duckdb/functions/string.py`
direct helpers diverged from engine semantics —
`starts_with`/`ends_with`/`contains` crashed with raw `TypeError` on
empty (None) argument collections where engines return `{}` and on
non-String args (engines raise a typed error), `substring(None)`
crashed, and `substring(1, -2)` returned `{}` while BOTH engines return
`''`. Fixed via `_validate_string_arg` (None → empty result, non-str →
`FHIRPathFunctionError`) plus the length<=0 → `''` parity fix.
Regression: `TestStringHelperEngineContractFp09Historian` in
`fhir4ds/fhirpath/duckdb/tests/unit/test_string.py`. Probe-trap note:
`fhirpath()` serializes Integers as strings — write native-path
indexOf expectations as `['1']`, not `[1]`.

**FP-09 spec-compliance EXPLORER confirmation (2026-08-17): §5.6.1-§5.6.5
clean; chunk closed.** Third personality on string search (82 fresh
dual-path adversarial chaining checks + 10 is_valid checks in
`/mnt/d/fhir4ds/.temp/qa/fp09_explorer3_2026_08_17/probe.py`): zero parity
diffs, zero spec violations, conformance 2832/2832 held, no code changes.
Verified-clean seams (do not "fix"): indexOf feeding substring (incl.
indexOf→-1 → `{}`), substring→endsWith composition, startsWith|endsWith
union filters in `where($this...)`, search functions inside select/repeat/
all/exists with `$this`/`$index` (repeat fixpoints terminate via `=`
dedup), wrong-typed FHIR fields (object-valued `Coding.code`, integer
`display`, boolean fields, absent paths) → singleton-String error → empty
identically in both engines, empty/multi-item/non-String expression
arguments → empty both, NFD combining code-point positions (indexOf past
a combining pair → 2), NFC-vs-NFD contains correctly false (no Unicode
normalization — byte/code-point identity), ZWJ and astral-plane
boundaries, 10k-char strings, empty needles (`''.indexOf('')` → 0,
`contains('')` → true). PROBE TRAP: `'a'.repeat($this & 'b')` is an
infinite-growth fixpoint (dedup never converges) — never put unbounded
growth projections in a probe; both engines grow forever, spec-consistently.
Also: `\U0001D400` is NOT a FHIRPath escape (only `\uXXXX` is) — both
engines treat it as literal ASCII text. Chunk tally: SKEPTIC 1 fix +
1 LOW INTENDED, HISTORIAN 1 fix + convention-pin correction, EXPLORER clean.

### FHIRPath Direct Math Helper Semantics

**Fixed in FP-11 HISTORIAN math audit (2026-05-17).** Exported direct helpers in `fhir4ds/fhirpath/duckdb/functions/math.py` are public enough to keep aligned with §5.7 semantics, not only with Python built-ins. `round_fn()` uses FHIRPath half-away-from-zero rounding, rejects non-Integer or negative precision, and avoids Python's bankers-rounding behavior.

**Fixed in FP-11 SKEPTIC iter 1 (2026-06-28).** Native C++ Quantity
`+`/`-`/`*`/`/` arithmetic at
`extensions/fhirpath/src/fhirpath/evaluator.cpp:7107-7166` used `double`
arithmetic and produced a result FPValue with empty `source_text`, causing
the `.value` projection at `evaluator.cpp:2646-2669` to leak raw binary64
noise (e.g. `(0.1 'mg' + 0.2 'mg').value` returned `0.30000000000000004`
instead of `0.3`). This was the deferred §5.7 root cause from FP-08
SKEPTIC. The surgical fix introduces a reusable helper
`normalizeQuantityArithmeticSourceText(double &value, bool
apply_integral_normalize = true)` at `evaluator.cpp:2125` that mirrors
FP-08 SKEPTIC's precision-15 shortest-round-trip mask AND re-parses the
shortest text back to `double` via `strtod` to re-anchor to the
nearest-double matching Python's `float(Decimal('0.3'))`. The re-parse
step is critical: `float(Decimal('0.3'))` is `0x3FD3333333333333` but
`0.1 + 0.2` (binary64 arithmetic) is `0x3FD3333333333334` — 1 ULP larger.
The helper is applied at all 8 Quantity arithmetic result sites at
`evaluator.cpp:7216/7230/7244/7251/7266/7273/7289/7303`. The
`apply_integral_normalize=true` parameter (default, used for `+`/`-`)
mirrors Python's `_normalize_quantity_value` integral-quantize rule;
`apply_integral_normalize=false` (used for `*`/`/`) mirrors Python's
`__mul__`/`__truediv__` non-normalizing behavior. The general lesson:
every native C++ Decimal-producing arithmetic path on FHIRPath Quantity
values MUST both (a) populate source_text with shortest-round-trip text,
AND (b) re-anchor the double field to `strtod(source_text)` so that
`toNumber()` (which ignores source_text) returns the same double as the
Python fallback. Audit pattern: `grep -n "quantity_value ="
extensions/fhirpath/src/fhirpath/evaluator.cpp` returns all
Decimal-producing Quantity sites; each one without a matching
`source_text = normalizeQuantityArithmeticSourceText(...)` call is a
binary64-drift leak candidate. Spec citations: FHIRPath v2.0.0 §5.7.1
(arithmetic on Quantity operands requires Decimal semantics), §4.1.4
(System.Decimal is "rational number with implicit precision" — not
binary64 noise), §4.1.8 (Quantity.value is Decimal). Regression
coverage: `test_arithmetic_parity.py::
test_quantity_arithmetic_value_no_binary64_drift_fp11_skeptic` and
`test_quantity_arithmetic_no_binary64_drift_dot_value_fp11_skeptic`. After
native changes, rebuild and copy the bundled
`fhirpath.duckdb_extension` to dev and user install paths.

### CQL Structural Type Operators

**Fixed in CQL-05 SKEPTIC/HISTORIAN/EXPLORER structural audit (2026-05-17).** CQL `is`, `as`, and `convert` must validate unknown structural targets and treat `List<T>`, `Interval<T>`, `Choice<T...>`, and `Tuple { ... }` as first-class type specifiers. Static aliases should preserve exact List, Interval, Ratio, Date, DateTime, Time, and Tuple identity. `as Quantity` over FHIR values must preserve `parse_quantity`/Quantity shape for downstream unit-aware comparisons. Numeric fallback for optimized quantity CTEs must not ignore incompatible units when the dynamic side is a JSON Quantity object. `Message(..., 'Error', ...) as Interval<T>` preserves `CQLMessage`, dynamic `as Concept`/`as Code` keeps runtime CodeableConcept/Coding matching, and SQL CASE sources produced by choice `as` casts remain valid FHIRPath property-navigation sources. `Children()`/`Descendants()` use internal typed transport for primitive child items, including temporal and Long values, so downstream `is`/`as` and `List<T>` checks do not coerce strings or erase identity. `convert <Quantity> to String` shares the `QuantityToString` path used by `ToString(<Quantity>)`; `convert List<Code> to Concept` and `convert Concept to List<Code>` are registered DuckDB UDF surfaces. Forced Python fallback tests must directly register Python FHIRPath UDFs, assert `fhirpath_predicate` is absent, and keep choice-field `value.is/as(Type)` parity with native execution. `as Concept` over FHIR resource properties should preserve resource/path information for value-set and coding matching.

Fresh CQL-05 SKEPTIC rerun (2026-05-30) added four guardrails: `convert ... to Any` must preserve the source runtime type for later `is`/`as` assertions; `ToQuantity(...)` SQL must be recognized as Quantity-shaped for nested `convert Quantity to String`; composite typed nulls such as `(null as List<Integer>) is List<Integer>` return false rather than SQL NULL; and `QuantityToString` must normalize JSON integer values to the CQL Quantity string pattern with at least one decimal digit, e.g. `5.0 'mg'`.

Fresh CQL-05 EXPLORER rerun (2026-05-30) added two recursive/inlining guardrails: `Children()`/`Descendants()` translation must recursively wrap nested tuple/list Date, DateTime, Time, and Long values with `__fhir4ds_cql_type` transport markers before handing them to `cqlChildren`/`cqlDescendants`, and all function-inliner `BinaryExpression` cloning paths must preserve `strict=True` so `cast` remains exception-raising inside inlined functions.

## Asset Relocation Reference

- **C++ Source:** `extensions/fhirpath/` and `extensions/cql/`
- **Web Demos:** `web/wasm-demo/` and `web/website/`
- **Benchmarks:** `benchmarks/`
- **Conformance Runner:** `fhir4ds/dqm/tests/conformance/`
- **Test Data:** `tests/data/` (submodules: ecqm-content-qicore-2025, dqm-content-qicore-2026)
- **Conformance Output:** `tests/output/` (gitignored, regenerated by conformance runner)
- **Benchmark Output:** `benchmarks/output/` (gitignored, regenerated by run_comparison.py)

---

## WASM / Pyodide Release Checklist

This section documents the recurring release steps required to keep the WASM demo working. Missing any of these steps causes Pyodide initialization failures in the CQL playground.

### Why This Breaks Every Release

`fhir4ds-v2` lists `duckdb~=X.Y.Z` as a Python dependency in `pyproject.toml`. In the browser, DuckDB is provided by **DuckDB-WASM** (JavaScript). There is no pure Python wheel for `duckdb` on PyPI — micropip cannot install it. This causes micropip to fail before the fhir4ds wheel is installed.

Additionally, `fhir4ds/cql/__init__.py` has a top-level `import duckdb` that must succeed at import time in Pyodide, even though DuckDB connections are never used in the translation code path.

Both issues are permanently mitigated:
1. **`fhir4ds/cql/__init__.py`**: `import duckdb` is wrapped in `try/except ImportError` that installs a minimal stub. The CQL translator works without the real duckdb package.
2. **`web/wasm-demo/src/workers/pyodide.worker.ts`**: Uses `micropip.install(wheel, deps=False)` and manually installs only the pure-Python deps (`antlr4-python3-runtime`, `python-dateutil`).

### Release Steps for WASM Demo

Every release must complete **all** of the following steps:

1. **Build the wheel:**
   ```bash
   cd /path/to/fhir4ds
   hatch build -t wheel
   # Output: dist/fhir4ds_v2-X.Y.Z-py3-none-any.whl
   ```

2. **Copy the wheel to `public/`:**
   ```bash
   cp dist/fhir4ds_v2-X.Y.Z-py3-none-any.whl web/wasm-demo/public/
   ```
   The `vite.config.ts` auto-discovers the newest `fhir4ds_v2-*.whl` in `public/` at build time. Remove the old wheel to avoid confusion.

3. **Remove the old wheel:**
   ```bash
   # Keep only the current version
   ls web/wasm-demo/public/fhir4ds_v2-*.whl
   rm web/wasm-demo/public/fhir4ds_v2-OLD_VERSION-py3-none-any.whl
   ```

4. **Update version references in docs and wasm-engine.md:**
   Search `web/website/docs/` and `web/wasm-demo/` for `fhir4ds_v2-OLD_VERSION` and update to the new version.

5. **Update `__version__` in subpackages:**
   All four subpackages must be updated to the new version:
   - `fhir4ds/cql/__init__.py`
   - `fhir4ds/dqm/__init__.py`
   - `fhir4ds/fhirpath/__init__.py`
   - `fhir4ds/viewdef/__init__.py`
   
   The root `fhir4ds/__init__.py` version is set by `pyproject.toml` via hatch; subpackage `__version__` strings must be updated manually.

6. **Build the WASM demo:**
   ```bash
   cd web/wasm-demo && npm run build
   ```

7. **⚠️ Deploy the build to the website static directory:**
   ```bash
   # Remove old build and replace with the fresh one
   rm -rf web/website/static/wasm-app
   cp -r web/wasm-demo/dist/. web/website/static/wasm-app/
   ```
   **This step is critical.** The website (`web/website/`) serves the WASM demo from
   `static/wasm-app/` — a pre-built snapshot that is NOT automatically updated when
   `web/wasm-demo/` is rebuilt. Skipping this step causes the website's CQL playground
   to silently use the stale build (old worker without `deps=False`, old wheel name, etc.)
   while the standalone demo works correctly, making the bug hard to diagnose.

8. **Run Playwright tests to verify (standalone + web component):**
   ```bash
   cd web/wasm-demo && npx playwright test tests/e2e/playground.spec.ts tests/e2e/web-component.spec.ts
   # All 11 tests must pass
   ```

### Pyodide Dependency Constraints

The Pyodide worker (`web/wasm-demo/src/workers/pyodide.worker.ts`) installs deps with `deps=False` and manually lists the required pure-Python deps:
- `antlr4-python3-runtime>=4.10` — CQL grammar parser
- `python-dateutil>=2.8` — date/time arithmetic in CQL

If new pure-Python dependencies are added to `fhir4ds-v2` that are required for CQL translation (not just data loading), they must be added to this manual install list in the worker.

**Do NOT add duckdb to this list.** DuckDB is provided by DuckDB-WASM and the Python stub in `fhir4ds/cql/__init__.py` handles the import-time reference.

### CQL Message Operator Fragile Area

**Fixed in CQL-22 SKEPTIC (2026-05-20).** `Message(source, condition, code, severity, message)` is generic over `source` and severity is a runtime `String` expression. Do not optimize nonliteral severity arguments to the bare source; parameters, definition references, and included-library inlined parameter names such as `ErrorLevel` must still reach `CQLMessage` so runtime `Error` severity stops evaluation. The public DuckDB `CQLMessage` surface must preserve the physical type of `source`; it should be a typed SQL macro around `error(...)`, not an effective string-returning Python UDF.

**CQL-22 HISTORIAN confirmation (2026-05-20).** This behavior is intentional
and spec-compliant: `Trace`, `Message`, and `Warning` severities continue
evaluation and return the unmodified source, including list and tuple sources;
only runtime `Error` severity stops evaluation. Keep parity checks covering
forced Python fallback and native-loaded DuckDB registrations.

**CQL-22 EXPLORER finding (2026-05-20).** The `Error` boundary must still stop
evaluation when optional `code` or `message` operands are SQL NULL. DuckDB
`error(NULL)` and NULL string concatenation can silently return SQL NULL, so
`CQLMessage` must coalesce nullable error text before calling `error(...)`.
Fixed in the DuckDB macro and Python fallback body with parity coverage for
forced Python fallback and native-loaded registrations.

**CQL-22 EXPLORER launch-3 finding (2026-08-23).** Queries over scalar
fhirpath navigation sources with an alias and BOTH where and return clauses
(`Patient.name N where <cond> return N.given`) silently dropped the where
clause — unfiltered lists per patient and swallowed Error-severity
`Message` raises (CQL 1.5 §9 + App B). Root cause in
`fhir4ds/cql/translator/expressions/_query.py`: the WHERE application
CASE-wrapped the whole scalar source, then the RETURN clause's
`_did_list_transform` path rebuilt `result` from the raw source call and
discarded that CASE. Fixed by deferring the where into the per-element list
path (`list_filter` before `list_transform`; a WHERE clause in the UNNEST
variant when the where/return body contains subqueries). Lesson: when two
clause handlers each rebuild `result`, audit what the second one drops.
Regression: `test_message_parity.py::test_cql_message_where_clause_in_navigation_query_applies_per_element_cql22_explorer`.
Also observed (pre-existing, bisected, out-of-chunk): `test_audit_mode.py`
`TestMinMaxAttribution::test_{min,max}_on_query_uses_arg_{min,max}` fail on
the cumulative uncommitted tree even with this launch's change disabled —
conformance gate unaffected; flagged for human review.

### Performance Scaling Probe

**NOT A BUG (Release 0.0.6 Domain 7, 2026-05-20).** Synthetic Patient loading
through `FHIRDataLoader.load_resources()` showed stable linear cost from 1k to
50k rows, with proportional tracemalloc peak growth and linear FHIRPath wrapper
query execution. Do not classify normal row-proportional slowdown as a
performance defect; Domain 7 findings require a qualitative scaling cliff,
memory spike, leak, or concurrency failure.

### Source Adapter API Errors

**Fixed in Release 0.0.6 Domain 8 (2026-05-20).** Source-adapter public
constructor argument validation should happen before SQL construction or DuckDB
registration. `CSVSource` rejects non-string `path`/`projection_sql` with
`TypeError` and empty required strings with `ValueError`; projection/view shape
errors still belong to `SchemaValidationError`.

**Fixed in Release 0.0.8 Domain 8 (2026-06-07).** `FileSystemSource` follows
the same public constructor boundary: non-string `path_pattern`/`format`
arguments raise `TypeError`, and empty strings raise `ValueError`, before
cloud-prefix checks, SQL literal quoting, or DuckDB registration.

### DQM Configuration API Contract

**Fixed in Release 0.0.8 Domain 8 (2026-06-07).** DQM run, HAPI
materialization, and Mongo materialization config loaders wrap malformed JSON
or YAML in `DQMConfigError` instead of leaking decoder internals. Nested
`libraries` and `terminology` sections must be objects before reading
`paths`/`valuesets`; malformed section shapes should raise `DQMConfigError`
with the field name, not `AttributeError`.

### DQM Audit Evidence Boundary

**Fixed in Release 0.0.6 Domain 9 (2026-05-20).** `AuditEngine.prune_evidence()`
is row-oriented: it expects a dict keyed by the population column name so it can
read the result/evidence for that population. Evaluator code that prunes one
cell at a time must wrap the cell as `{col_name: cell}`. Passing the raw audit
cell erases causal evidence and causes narratives/exports to report missing
detail incorrectly.

**Fixed in Release 0.0.8 Domain 9 (2026-06-07).** Multi-group DQM audit
pruning must run only against the current group. Passing each group DataFrame
through every `PopulationMap` group can compact evidence more than once and
erase resource targets in the final findings. Materialized compact result JSON
must also stay audit-free: HAPI and Mongo materialization should unwrap audit
structs to their `result` value and keep supporting evidence columns only in
the full audit JSON.

### Release Version Consistency

**Fixed in Release 0.0.6 Domain 10 (2026-05-20).** Public subpackage
`__version__` values in the unified namespace should match `fhir4ds.__version__`.
Keep `fhir4ds/tests/test_version.py` release-neutral by comparing against the
root package version rather than hardcoding the current version.

**Fixed in Release 0.0.8 Domain 10 (2026-06-07).** Release metadata and public
versions must also include `fhir4ds.cql.duckdb.__version__`, not only the root
and major feature packages. Keep `pyproject.toml`, public subpackage
`__version__` constants, notebook install snippets, wheel metadata, and the
bundled-extension wheel contents aligned with the release target.

**Fixed in Release 0.0.8 Hardening 14 (2026-06-07).** Conformance-facing
version metadata is part of the release surface. The CQL tests-runner facade
must emit `cqlTranslatorVersion` and `cqlEngineVersion` from
`fhir4ds.__version__`, not a hardcoded prior release.

**Fixed in Release 0.0.8 Hardening 17 (2026-06-07).** Website and WASM demo
assets are part of the release surface. The homepage version badge, website
tests, WASM integration docs, notebook docs, release notes, demo public wheel,
and `web/website/static/wasm-app/` snapshot must all be refreshed for the
target version. Keep `web/wasm-demo` build plus website typecheck/build in the
release gate.

### HEDIS Continuous Enrollment Primitives

**NOT A BUG (Release 0.0.6 Domain 11, 2026-05-20).** Continuous-enrollment
temporal primitives matched across forced Python fallback, native-loaded, and
no-Python C++ surfaces: overlapping/adjacent coverage intervals collapse,
one-day uncovered gaps remain separate, `successor of end` advances exactly one
day, and 45/46-day plus total-small-gap threshold comparisons evaluate
correctly. If adding a dedicated enrollment helper, keep these primitives
parity-tested together.

### HEDIS Age Boundary Semantics

**Fixed in Release 0.0.6 Domain 12 (2026-05-20).** CQL age helpers use complete
calendar periods, not raw day counts or simple month/day tuple comparison. Feb
29 birthdays use the last valid day in non-leap years, so
`CalculateAgeInYearsAt(@2000-02-29, @2021-02-28)` is `21`, and complete-month
calculation follows the same calendar-month add rule. Keep forced Python
fallback, native-loaded, no-Python C++ runtime, and patient-context translated
`AgeIn*At()` SQL parity-tested together.

### HEDIS Episode Dedup Aggregate Boundary

**Fixed in Release 0.0.6 Domain 13 (2026-05-20).** HEDIS-style episode
deduplication depends on CQL query `aggregate` with a typed empty list starting
value such as `({} as List<Date>)`. Typed empty lists must compile to typed
DuckDB arrays, list-accumulator aggregates must use the recursive fold path,
`Count(R)` inside the fold must count list elements rather than emitting a SQL
row aggregate, and `Count(<fold result>)` must treat the fold output as a list.
Keep sorting-before-fold, empty input, same-day collapse, exact 31-day collapse,
and 32-day new-episode cases parity-tested across forced Python fallback,
native-loaded, and no-Python C++ surfaces.

### HEDIS Hospice Extension Predicates

**Fixed in Release 0.0.6 Domain 14 (2026-05-20).** Nested extension predicates
such as `exists(Coverage.extension Ext where Ext.url = '<url>')` must be
existential over all repeated extensions. Do not lower extension URL equality
to scalar `fhirpath_text(resource, 'extension.url') = '<url>'`; that only sees
one projected value and can miss a later LTI/hospice extension. Route
`extension.url` equality through `fhirpath_bool(resource,
'extension.where(url=''<url>'').exists()')` and keep multi-source OR,
empty-source short-circuiting, temporal measurement-period bounding, and
multi-extension coverage cases parity-tested across forced Python fallback,
native-loaded, and no-Python C++ surfaces.

### HEDIS FHIR Choice Type Assertions

**NOT A BUG (Release 0.0.6 Domain 15, 2026-05-20).** Current translated
choice-type assertions handle the tested HEDIS effective[x] boundaries:
`effectivePeriod as FHIR.dateTime` returns NULL, `date from (effective as
FHIR.dateTime)` strips the date from an `effectiveDateTime`, and
`effectiveDate as FHIR.date` remains distinct from `FHIR.dateTime`. Keep these
assertion/extraction cases parity-tested across forced Python fallback,
native-loaded, and no-Python C++ surfaces when changing choice-type logic.

### HEDIS Interval Boundary Semantics

**NOT A BUG (Release 0.0.6 Domain 16, 2026-05-20).** Current translated CQL
interval boundaries match the HEDIS expectations tested in the release loop:
closed intervals sharing one endpoint overlap, equal closed intervals satisfy
`during`, `within 15 days of` is inclusive at 15 and false at 16,
`same day or after` includes equality, and `starts/ends during day of`
measurement-period endpoints include the first/last day. Keep these boundaries
parity-tested across forced Python fallback, native-loaded, and no-Python C++
surfaces when changing temporal interval operators.

### HEDIS Multi-Group Population Isolation

**NOT A BUG (Release 0.0.6 Domain 17, 2026-05-20).** Current DQM
`summary_report()` computes per-group summaries from each `_group_id` slice, so
denominator exclusions in one independent rate group do not remove numerator
or denominator membership from another group. The top-level summary over a
concatenated multi-group DataFrame is an aggregate convenience view; consumers
that need official rate-group counts should use `summary["groups"][group_id]`
or the generated MeasureReport groups.

### DQM Stratifier Propagation

**Fixed in Release 0.0.6 Domain 18 (2026-05-20).** DQM `Measure.group.stratifier`
entries are part of the reporting contract, including payer/reporting-line
strata. Parse simple criteria stratifiers and composite component stratifiers,
evaluate their CQL expressions as generated `stratifier_*` columns, and export
stratum population counts in `summary_report()` and generated MeasureReport
groups. For mutually exclusive reporting-line stratifiers, keep a total
validation that the sum of initial-population stratum counts equals the group
initial population.

### HEDIS Reference Resolution

**Fixed in Release 0.0.6 Domain 19 (2026-05-20).** CQL/FHIR reference
resolution must accept the same id-tail semantics used by QICoreCommon
`GetId()`/`getId()`/`references()`: `ResourceType/id`, bare ids, full URLs
ending in `ResourceType/id`, and JSON `Reference` objects containing those
forms all resolve to the target resource id. Keep `resolve()` macro behavior
aligned between `FHIRDataLoader` registration and the DuckDB clinical macro
module. `singleton from` may return NULL or raise for multi-item inputs
depending on the translated/direct surface, but it must never silently pick an
arbitrary element.

## Iteration 6 / Domain 8 SKEPTIC (Error Handling) — 2026-07-05

QA-011 (HIGH): `__version__` strings in 7 `__init__.py` files are stale
at `0.0.10` while `pyproject.toml` targets `0.0.11`. Files:
`fhir4ds/__init__.py:24`, `fhir4ds/cql/__init__.py:82`,
`fhir4ds/cql/duckdb/__init__.py:10`, `fhir4ds/fhirpath/__init__.py:18`,
`fhir4ds/fhirpath/duckdb/__init__.py:21`, `fhir4ds/dqm/__init__.py:34`,
`fhir4ds/viewdef/__init__.py:27`. Release blocker — every release bump
must hand-edit all 7 sites. Recommend consolidating to
`fhir4ds/_version.py` source of truth + a pytest that asserts
`fhir4ds.__version__ == importlib.metadata.version('fhir4ds-v2')`.


## Milestone code review (2026-08-17, FP-01..FP-05 campaign diff)

Line-by-line review of the uncommitted campaign diff (26 files, +4,342/−779)
is in `fhir4ds-private/docs/prompts/.ai_loop/code_review_findings.md`. No
CRITICAL/HIGH findings. Three filed issues: REV-001 LOW (unguarded
`std::stoi` on sign-only suffix in `fhirpathSplitUnitTerm` — currently
masked, add a digits-consumed guard when touching it), REV-002 MEDIUM
(FHIR type metadata hand-duplicated between native C++ tables and
`models/r4` JSON — generate the native table from metadata when next
touched), REV-003 LOW (unrelated untracked files + tracked clangd cache
in the working tree; stage campaign files explicitly, never `git add -A`).

### FHIRPath FP-08 spec-compliance SKEPTIC §5.5.7-§5.5.9 audit (2026-08-17, spec-compliance campaign)

137 fresh dual-path probes over toQuantity/convertsToQuantity,
toString/convertsToString, toTime/convertsToTime. Three fixes (all
RESOLVED, extension rebuilt + redeployed, conformance 2832/2832 held):

- **§5.5.7 has its own conversion-factor table (QA-001, MEDIUM).** The
  June calendar-vs-UCUM group separation must not block
  calendar-keyword↔calendar-keyword conversion in toQuantity:
  `(1 year).toQuantity('day')` → `365 day`, `(1 month).toQuantity('day')`
  → `30 day`, year↔month keeps the DIRECT factor 12 (365/30 ≠ 12).
  Implemented as a toQuantity-only table:
  `FP_Quantity.conv_duration_to_spec` (engine/nodes.py, called only from
  `to_quantity`) and native `durationSpecMagnitude` +
  `exactDecimalRatioText` in `convertQuantityUnit` (evaluator.cpp, single
  caller `fn_toQuantity`). Equality/ordering/arithmetic grouping
  (12×30=360 ≠ 365 doctrine) is untouched, and calendar↔UCUM cross
  conversion (`1 year -> 's'` empty) stays rejected.
- **Decimal conversion parity is 28 significant digits (QA-002,
  MEDIUM).** Native duration conversions now use exact __int128 long
  division rendering 28 sig digits ROUND_HALF_EVEN (§4.1.4) instead of
  the binary64 15-sig-fig mask: `(1 's').toQuantity('min')` →
  `0.01666666666666666666666666667 'min'` in BOTH engines.
- **FP_Time strptime needs all partial forms (QA-003, HIGH).** Without
  `"T%H:%M"`, `"T%H"`, and bare `"%H"` in the format list, T-prefixed
  partial times get no `_pyTimeObject` and
  `'T14:34'.toTime() = @T14:34` returned false in the fallback while
  native returned true.
- Stale unit expectations `test_plus_days_preserves_timezone_z` (both
  copies under fhir4ds/fhirpath{,/duckdb}/tests/unit) updated to the
  FP-07 Z-preservation doctrine (`Z` appended verbatim).
- Regression coverage:
  `fhir4ds/fhirpath/duckdb/tests/integration/test_fp08_spec_quantity_time_parity.py`.
- Environment: DuckDB caches extension copies in
  `~/.duckdb/extensions/<ver>/<arch>/`; `INSTALL '<path>'` does NOT
  reliably overwrite them — after rebuilding, copy the new
  `fhirpath.duckdb_extension` to the repo bundle, site-packages, AND the
  ~/.duckdb caches (or LOAD by absolute path in probes) or probes will
  silently test a stale binary. Repo also carries an unrelated
  pre-existing `stash@{0}: On main: tmpcheck` — do not pop it.

### FHIRPath FP-08 HISTORIAN §5.5.7-§5.5.9 audit (2026-08-17, spec-compliance campaign)

Second personality on Quantity/String/Time conversion (117 fresh
dual-path probes, /mnt/d/fhir4ds/.temp/qa/fp08_historian_2026_08_17/).
All 3 SKEPTIC fixes re-verified spec-correct and regression-free (duration
table incl. plurals/roundtrips, 28-sig-digit rendering on fresh variants,
T-prefixed partial toTime forms). Two MEDIUM fixes, both Python-side
(native already correct; NO extension rebuild):

- **QA-001 (PARITY): terminating unit conversions rendered Decimal
  scale artifacts in the fallback** (`180 'cm'.toQuantity('m')` →
  `1.80 'm'` vs native `1.8 'm'`; also `6.0 'min'`, `1.000 'ms'`,
  `8.000... hour`, roundtrip `1.000...000 's'`). Fix:
  `FP_Quantity._divide_and_render` (engine/nodes.py) — exactness decided
  by `Fraction` on the PRE-division numerator/denominator; exact
  terminating quotients trim trailing zeros, non-terminating quotients
  keep the 28-sig-digit ROUND_HALF_EVEN rendering verbatim (the trailing
  zero in `1 day → 0.002739726027397260273972602740 year` is a rounding
  result, NOT scale). CRITICAL LESSON: an after-the-fact exactness check
  on the Decimal RESULT is always wrong — every finite Decimal looks
  terminating; the existing SKEPTIC regression test caught it. Applied
  at conv_duration_to_spec and the weeks/days + m/cm branches of
  conv_unit_to; comparison/arithmetic callers are Decimal-scale-
  insensitive, verified by the full fhirpath tree (1745 passed).
- **QA-002 (SPEC_VIOLATION): direct helper to_quantity missed the §5.5.7
  duration table** — `functions.conversion.to_quantity("1 'year'", "day")`
  returned None while the engine returns `365 day`. `_convert_quantity`
  now routes through `conv_duration_to_spec` first (FP-09 direct-helper
  doctrine).
- Regression coverage: 2 new tests in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_fp08_spec_quantity_time_parity.py`.
- Verified clean (do not "fix"): convertsToQuantity(unit-arg) full
  routing; conversion results inside where/select/all/iif/repeat;
  resource-driven valueQuantity/valueString conversions; toString/
  convertsToString all literal types + empty/multi-item doctrine;
  toTime/convertsToTime full grammar matrix; wrong-typed unit args
  (Integer/Boolean/empty-string) → empty identically; is_valid parity
  (17 forms). fhirpath() serializes booleans as strings ("true") —
  probe expectations must use string form. ~/.duckdb cache can raise
  "Metadata mismatch" on LOAD even with identical md5 — LOAD by
  absolute path in probes. Conformance 2832/2832 held.

### FHIRPath FP-08 EXPLORER §5.5.7-§5.5.9 audit (2026-08-17, spec-compliance campaign)

Third personality on Quantity/String/Time conversion (95 fresh dual-path
probe cases, /mnt/d/fhir4ds/.temp/qa/fp08_explorer3_2026_08_17/probe.py).
Both fixes verified, conformance 2832/2832 held, fhirpath tree 1745 passed:

- **QA-001 (HIGH, FIXED): fallback `conv_unit_to` never converted
  direct-`_ucum_base_conversion_factor` keys.** The base-reduction fallback
  was guarded on `_unit_reduces_to_base()`, which deliberately returns
  False for direct keys — so derived families (J/kJ, N/kN, W/kW, V/mV),
  exponent keys (m2/cm2), and direct→expression pairs ('kJ'→'kg.m2/s2')
  returned empty/false in the Python fallback while native converted.
  Fix: direct-key base bridge in `conv_unit_to` (nodes.py) that reduces
  both sides via `conv_unit_to_base`, EXCLUDING base unit `'s'` so the
  calendar-vs-UCUM doctrines (1 year → 's' empty, 1 'month' = 1 'mo'
  empty, fixture-pinned) and offset-temperature rejections stay intact.
  DOCTRINE GUARD: never let the generic base bridge touch the seconds
  base — the §5.5.7 category table and §6.1.1 fixtures outrank generic
  commensurability for time-valued units.
- **QA-002 (MEDIUM, FIXED): native metric conversions rendered at binary64
  15-sig-digit precision** (`(1 'kPa').toQuantity('mm[Hg]')` →
  7.50063755419211 vs the fallback's 28-digit Decimal). Fix:
  `decimalFactorRatio()` + an exact branch in `convertQuantityUnit`
  (evaluator.cpp) routing through the existing `exactDecimalRatioText`
  (§4.1.4: 28 sig digits ROUND_HALF_EVEN); guards fall back to binary64
  for exotic inputs (scientific-notation text, >25-digit values). Shared
  `ucum_units.hpp` untouched — CQL extension not rebuilt.
- Regression coverage: 2 tests in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_fp08_spec_quantity_time_parity.py`.
- Shared-convention pins (do not "fix"): `toQuantity('')` /
  `convertsToQuantity('')` act as the no-argument form in BOTH engines
  (' ' with a space is correctly rejected); `'180 cm'` /
  `'5 mg'` string inputs are NOT parsed as quantities (bare UCUM codes in
  strings rejected; only calendar keywords and quoted units parse);
  `(-0.0).toString()` → `0.0` (FP-01 QA-005).
- Verified clean: toString of every literal type at extremes (32-bit
  bounds, 28-digit decimals, negative quantities, all calendar keyword
  spellings, offset/leap-second-adjacent temporals); toString/
  convertsToString on collections/resources/empty/multi-item; toTime of
  dateTime strings and partial times with offsets; convert→convert
  roundtrips; converted values feeding equality/ordering/arithmetic/
  membership/distinct/.value.

### FHIRPath FP-10 spec-compliance SKEPTIC rerun (2026-08-17): §5.6.6-§5.6.12 string transform

Fresh dual-path audit (82 + 31 probe cases + helper comparisons,
/mnt/d/fhir4ds/.temp/qa/fp10_skeptic2_2026_08_17/). Verified clean: upper/lower
Unicode case mapping both engines (ß→SS, ς↔Σ, ﬃ→FFI, İ lower to i+U+0307,
CJK/Deseret/Georgian/Armenian, prior-launch native tables intact); replace()
literal all-instances semantics incl. metachar-as-literal, ''-pattern
xaxbxcx, ''-substitution removal, astral replacements; matches partial-match
semantics, single-line default, backreferences, lookahead, \Z; replaceMatches
global replacement, $N/$0/${name}/$$, spec date example; length()/toChars()
code-point semantics incl. astral and combining sequences; empty/multi-item/
non-string/arity/invalid-flag/ReDoS classification parity. Five fixes (all
RESOLVED; extension rebuilt + redeployed to repo bundle and ~/.duckdb caches):

- **QA-001 (MEDIUM): native default-mode `$` lacked PCRE trailing-newline
  match** ('abc\n'.matches('abc$') native false vs fallback/PCRE true).
  Fix: normalizeFHIRPathRegex translates non-multiline unescaped `$` to the
  zero-width lookahead `(?=\n?$)` (CRLF stays false, matching PCRE/Python).
- **QA-002 (MEDIUM): native lacked PCRE inline flag groups.** Leading
  (?i)/(?m)/(?s) are folded into the effective flags by the new
  `applyInlineRegexFlags` at the fn_matches/fn_replaceMatches call sites
  (folding INSIDE normalize alone is insufficient — std::regex::icase comes
  from the compile options, not the normalization).
- **QA-003 (MEDIUM, doctrine): regex character classes are ASCII per the
  PCRE-recommended dialect.** Python \w/\d/\s/\b are Unicode-aware, diverging
  from PCRE-default and native on '日本語'.matches('\w+'), Arabic-Indic \d,
  NBSP \s, stra\b. Fix in the FALLBACK direction:
  `_translate_pcre_ascii_classes` (engine/invocations/strings.py) rewrites
  \w\W\d\D\s\S\b\B and POSIX [[:name:]] classes to ASCII-PCRE equivalents,
  shared by the direct helper. DO NOT use re.ASCII instead — it also disables
  Unicode case-insensitive matching ('É'.matches('é','i') must stay true).
- **QA-005 (MEDIUM): fallback syntax precheck rejected `$$` inside string
  literals** (replaceMatches('A','$$') is valid §5.6.10 syntax). Dollar-sign
  checks now run on `_mask_string_literals(text)` in both
  `_get_compiled_evaluator` and `fhirpath_is_valid_udf`.
- **QA-006 (MEDIUM, 5th instance of the "exported helper API forgotten"
  family): functions/string.py replace_matches passed the replacement
  straight to re.sub** — '$1' stayed literal and (?<name>...) patterns
  raised. It now delegates to the engine replace_matches; replace() gained
  _validate_string_arg guards.
- QA-004 (LOW, DEFERRED): lookbehind (?<=…) unsupported by std::regex —
  spec-sanctioned dialect difference (like named groups); pinned in
  test_string_transform_regex_dialect_documented_divergences_fp10_skeptic2.
  Also pinned there-by-handoff: bare `[:alpha:]` (no outer brackets) is a
  POSIX class natively but a char class in Python/PCRE — dialect corner.
- Probe traps this launch: (a) `\w` inside a FHIRPath string literal
  unescapes to `w` — write `'\\w+'` in test expressions; (b) editor can
  silently insert NBSP (U+00A0) into "a b" test data, flipping \s probes.

### FHIRPath FP-10 HISTORIAN rerun (2026-08-17): named capture groups now
### spec-compliant on BOTH engines

Second personality on §5.6.6-§5.6.12 (107 fresh dual-path cases,
/mnt/d/fhir4ds/.temp/qa/fp10_historian2_2026_08_17/probe.py). All 5 SKEPTIC
fixes re-verified intact. Two fixes, one pin; extension rebuilt + redeployed
(repo bundle, user site-packages, ~/.duckdb caches v1.3.0/v1.5.2);
conformance 2832/2832, fhirpath pytest tree 1774/1774.

- **QA-001 (HIGH, FIXED): the §5.6.10 canonical replaceMatches example now
  runs natively.** `(?<name>…)` named groups are translated to plain
  capturing groups inside `normalizeFHIRPathRegex` (evaluator.cpp — group
  order/numbering preserved; lookbehind `(?<=`/`(?<!` deliberately stays on
  the invalid path), and `translateNamedGroupSubstitution` +
  `fhirpathNamedGroupNumbers` rewrite `${name}` for EXISTING named groups
  to numbered `$N` before `std::regex_replace` (both the multiline
  line-wise and normal paths). Substitution pass-through doctrine: `$N`,
  `$$`, `$word`, `${unknown}`, `${N}` are literal/empty EXACTLY as in the
  Python engine — only `${name}` for an existing group is translated.
  LOCKSTEP RULE: the same `(?<name>…)` translation must live in ALL FOUR
  surfaces — native normalize, Python engine `matches()`
  (`_translate_named_groups` in engine/invocations/strings.py, shared with
  `replace_matches`), the direct helper `matches()`
  (duckdb/functions/string.py), and `udf.py::
  _has_invalid_string_regex_literals` (which previously reported
  is_valid=False for valid §5.6.10 syntax). Prior doctrine ("no named
  groups natively, like lookbehind") is SUPERSEDED: a dialect limitation is
  only spec-sanctioned when the spec's own examples don't depend on the
  feature. C++ gotcha: identifier scanners must probe single-char names —
  the initial emptiness guard rejected `(?<n>a)`.
- **QA-002 (MEDIUM, FIXED): direct helper `matches()` None-arg crash**
  (`len(None)` TypeError) — now None → empty collection, non-String →
  typed FHIRPathFunctionError (6th instance of the exported-helper-API
  family; always audit sibling helpers when fixing one).
- QA-003 (LOW, DEFERRED, dialect): mid-pattern inline flags `a(?i)B`,
  scoped flag groups `(?i:a)b`, and REGEX-level `\uXXXX` escapes (i.e. a
  literal backslash-u in the pattern text — NOT the FHIRPath `\uXXXX`
  literal escape) diverge: Python `re` supports them, std::regex and
  default PCRE do not. Pinned in
  `test_string_transform_regex_dialect_documented_divergences_fp10_skeptic2`.
- Verified clean: replace non-overlapping left-to-right scan with no
  rescan (`'aaa'.replace('a','aa')` → `'aaaaaa'`), case-sensitive replace,
  titlecase/ẞ/Kelvin/ﬅ/ẛ case mappings, empty-string regex semantics,
  single-line dot vs \n with negated-class contrast, dangling/`$ `/
  two-digit `$10` substitutions, toChars+indexer/first/last/count chains,
  `''→{}` corners for length/toChars/upper/lower.

### FHIRPath FP-10 EXPLORER rerun (2026-08-17): antlr STRING loop must be
### non-greedy; chunk closed

Third personality on §5.6.6-§5.6.12 (69 dual-path cases + is_valid checks,
/mnt/d/fhir4ds/.temp/qa/fp10_explorer3_2026_08_17/probe.py). One fix
(QA-001, MEDIUM, RESOLVED); everything else parity-clean: locale-sensitive
case mapping (Turkish ı/İ, Greek ς/Σ context-free, Cyrillic, fullwidth),
toChars/length code-point semantics on astral/ZWJ/regional-indicator/
combining inputs (consistent with FP-09 substring/indexOf), greedy-vs-lazy
replaceMatches, adjacent/nested-group captures, `(?m)/(?s)/(?i)` flags,
multiline anchors, regex sourced FROM resource fields, transforms inside
where/select/repeat, chained transforms, empty/multi-item/non-String/
arity corners. Conformance 2832/2832 held; fhirpath tree 1774, viewdef 1118.

- **QA-001: STRING literals ending in an escaped backslash mis-lexed before
  a comma.** `p.replace('\\','/')` failed to PARSE in the antlr fallback
  (native evaluated correctly; `fhirpath_is_valid` diverged True/False).
  Root cause: `FHIRPath.g4` STRING loop allowed raw backslash in the
  negated set, so ESC's `\'` alternative let maximal munch swallow the
  closing quote + comma, lexing `'lit\\','next'` as ONE token. Fix: make
  the STRING loop NON-GREEDY (`*?`) so the literal closes at the first
  quote terminating any alternative path; regenerate
  `fhir4ds/fhirpath/parser/generated/` with antlr4 4.13.1 (tool version
  must match the 4.13.x runtime). DOCTRINE: do NOT "fix" by aligning with
  the official `~['\\]` negated set — that breaks the tolerant
  raw-backslash corners BOTH engines accept and
  `test_literal_parity.py` pins (`'abc\'` → "abc", `'short \u005'` →
  "short u005"). Guard test:
  `test_string_transform_parity.py::test_escaped_backslash_argument_literals_lex_correctly_fp10_explorer`.
  LESSON: lexer-ambiguity fixes must re-run the literal-parity file first;
  native-vs-fallback PARITY (not the official grammar alone) is the
  binding constraint wherever no fixture pins the corner.
- Verified clean (do not "fix"): `(a+)+b` nested-quantifier regex → empty
  in BOTH engines (shared ReDoS guard); `max()` absent from the fallback
  registry (FP-02 EXPLORER doctrine); `'a\nb'.length()` → 3 (the ESC `\n`
  is a real newline).

FP-10 chunk tally: SKEPTIC 5 fixes + 1 LOW DEFERRED (lookbehind dialect),
HISTORIAN 2 fixes + 1 LOW DEFERRED (mid-pattern flags/\uXXXX dialect),
EXPLORER 1 fix (lexer). Chunk CLOSED.

## Milestone code review #2 (2026-08-17, FP-06..FP-10 delta)

- REV-001 (LOW, still open): `fhirpathSplitUnitTerm` still reaches
  `std::stoi("-")` for composed terms ending in `-` (no exponent digits
  stripped). Not literal-reachable; hardening only.
- REV-002 (MEDIUM, still open, widened): FP-08 added a third hand-maintained
  metadata pair — `nodes.py:_duration_spec_table`/`_ym_seconds_bridge` vs
  `evaluator.cpp:durationSpecMagnitude`. Aligned and parity-tested, but
  drift-prone; long-term fix is build-time generation from `models/r4`.
- REV-004 (LOW, new): `exactDecimalRatioText` long-division inputs can
  overflow `unsigned __int128` (digits x cross-ratio up to ~10^52 > 2^128)
  causing silent wraparound instead of bail-to-binary64. No current UCUM
  factor pair reaches it; add a magnitude budget guard when next touching.
- REV-005 (LOW, new): Python fallback passes mid-pattern inline regex flags
  (a(?i)B) to re.compile, which emits DeprecationWarning today and will
  error in a future CPython; native folds only leading flag groups. Pin a
  chosen behavior before Python removes the deprecated form.
- Verified clean: grammar fix is minimal (non-greedy loop only), iif scope
  semantics, \Z anchors, div Decimal promotion + guarded quantize,
  toQuantity spec duration table (both engines + direct helper), Z-suffix
  preservation, regex normalization symmetry, is_valid error-message
  coupling, masked dollar-pattern checks, extension binary rebuilt after
  the last evaluator.cpp edit. Validation: 149 passed (fp08 parity +
  string transform parity + unit string).
- Environment note: evaluator.cpp contains one literal NUL byte inside a
  comment (JSON escaped-NUL discussion, offset ~33139); benign, but grep
  and file treat the source as binary — strip NULs to a temp copy when
  scanning.

### FHIRPath §5.7 Math (FP-11 spec-compliance SKEPTIC, 2026-08-17)

Four dual-path fixes, extension rebuilt + redeployed (repo bundle,
site-packages, ~/.duckdb/extensions/v1.5.2):

1. **power() Integer typing (§5.7)**: "If this function is used with
   Integers, the result is an Integer" — Integer base + Integer exponent now
   returns an Integer (renders "8", not "8.0") on both engines; beyond the
   int64 range it degrades to exact Decimal-shaped text (engine doctrine,
   preserves (2).power(1024) exact digits); a negative Integer exponent on an
   Integer base returns empty (STU3 functions.json states this explicitly).
   Old pins in `test_math_parity.py` asserted Decimal and were updated.
2. **Exact Decimal power in native**: `powerDecimalExactText`
   (evaluator.cpp, replacing `powerIntegerExactText`) computes
   magnitude^|exp| by string multiplication, handles Decimal bases
   (1.1.power(2) -> 1.21, previously binary64 noise 1.2100000000000002) and
   negative integral exponents via `divideIntegerMagnitudeText` long
   division, rendered at 28 significant digits ROUND_HALF_EVEN by
   `roundDecimalTextHalfEvenSig` — which ZERO-FILLS dropped digits to
   preserve magnitude, mirroring Python's Decimal.normalize() under a
   28-digit context. Pure integer bases with positive exponents keep full
   exact digits (FP-11 EXPLORER 2026-06-29 doctrine).
3. **round() negative zero**: Python fallback `( -0.4 ).round()` serialized
   "-0.0" vs native "0.0"; `rround()` now copy_abs()es a zero result.
4. **power() non-integral exponents are transcendental**: both engines now
   render shortest-round-trip binary64 (Python routes through
   `math.pow(float...)`; native std::pow fallthrough sets
   `normalizeDecimalMathSourceText`), consistent with sqrt() which the spec
   calls "equivalent to raising a number to the power of 0.5".

Doctrine clarifications (verified against N1 2.0.0 spec/N1/index.adoc §5.7
and STU3 functions.json — NOT the launch brief's hints):
- round() is TRADITIONAL rounding (0.5 -> 1, -0.5 -> -1), not half-even.
- Transcendental §5.7 results (exp/ln/log/sqrt, power with non-integral
  exponent) render binary64 shortest-round-trip on both engines by pinned
  doctrine; the 28-digit ROUND_HALF_EVEN Decimal doctrine applies to
  rational results (exact arithmetic, UCUM conversions) only.
- KNOWN ACCEPTED DRIFT: native std::pow inside the extension can differ by
  <=1 ULP from libm pow used by Python math.pow (e.g.
  (0.001).power(1.37)); both engines render their own double minimally.
  Not a bug (QA-006 LOW INTENDED).

### FHIRPath FP-11 HISTORIAN §5.7 math audit (2026-08-17, spec-compliance campaign)

Second personality on §5.7 (81 fresh dual-path engine cases + direct-helper
probe, `/mnt/d/fhir4ds/.temp/qa/fp11_historian2_2026_08_17/`): engine parity
clean except the pinned <=1 ULP transcendental drift; all 4 SKEPTIC fixes
re-verified on both engines (Quantity operands, resource-driven math,
iteration chaining, log-base guards all fresh angles).

- **QA-001 (MEDIUM, FIXED — 7th "exported helper API forgotten" instance)**:
  the SKEPTIC engine fixes never reached
  `fhir4ds/fhirpath/duckdb/functions/math.py`. `power()` now mirrors engine
  §5.7 semantics (Integer base+exponent → int64 Integer; negative Integer
  exponent → empty; beyond int64 exact Decimal digits; integral Decimal
  exponents exact Decimal; non-integral exponents binary64 shortest-round-
  trip); `round_fn()` normalizes negative zero. Regression:
  `TestFp11HistorianMathHelperEngineContract` in
  `fhir4ds/fhirpath/duckdb/tests/unit/test_math.py`. Python-only, no
  extension rebuild. RULE: whenever a §5.7-family engine semantic changes,
  grep the direct-helper module for the same function before closing the
  chunk. Long-term: delegate direct helpers to engine implementations
  instead of parallel hand-maintained semantics (same family as REV-002).

### FHIRPath FP-11 EXPLORER §5.7 fixes (2026-08-17, spec-compliance campaign)

Third personality on §5.7; chunk closed (SKEPTIC 4, HISTORIAN 1+helper,
EXPLORER 2). Two native fixes, extension rebuilt + redeployed (repo bundle,
site-packages, ~/.duckdb v1.5.2):

- **QA-001 (HIGH): non-subnormal scientific Decimal renders must expand the
  shortest-round-trip text, not fixed<<setprecision(15).** Native
  `formatDecimalNumber` truncated significant digits behind leading
  fractional zeros (1e-27.sqrt() → '0.000000000000032', ~1% error; 1e-28
  .sqrt() → '0.0') and rendered large values as the exact binary64
  expansion. Canonical rendering (both engines): fixed expansion of
  `Decimal(str(float))` shortest-round-trip via
  `expandScientificToFixed(shortestRoundTripText(value))`; scientific form
  stays reserved for subnormals <1e-300. Transcendental VALUES remain
  binary64 — only the rendering was the bug.
- **QA-002 (MEDIUM): exact-power must not silently bail to std::pow where
  the fallback computes exact Decimal 28-sig.** Dropped the scale>20 guard;
  >10000-digit magnitudes route Decimal bases to
  `powerDecimalGuarded28Text` (log-time binary exponentiation) instead of
  std::pow (integer base + positive exponent keeps the documented
  exact-digit degrade); negative-exponent cap raised 100→10000 with the
  guarded-28 path beyond; long-division fractional digits raised to 10100
  (2.0.power(-1023) keeps 28 sig digits); `1^e` short-circuit (anti-DoS);
  subnormal-scale results (|v|<1e-300) render shortest-round-trip
  scientific ((0.5).power(1074) → '5e-324'). Remaining binary64 degrades
  (|exp|>1e15, 1M-char text) are documented anti-DoS bounds.
- Regression coverage:
  `test_math_parity.py::test_transcendental_tiny_decimal_rendering_parity_fp11_explorer2`
  and `::test_power_exact_decimal_no_bailout_parity_fp11_explorer2`.
  Conformance 2832/2832 held.
- DOCTRINE (probe technique): when an engine has two rendering/arithmetic
  regimes (fixed vs scientific; exact vs degrade), probe the TRANSITION
  boundaries between them — both defects lived there, invisible from each
  regime's interior.

### FHIRPath FP-12 spec-compliance rerun (2026-08-17): §5.8/§5.9

Fresh SKEPTIC dual-path audit (57 eval + 13 is_valid cases,
`.temp/qa/fp12_skeptic_2026_08_17/probe.py`). Two fixes, both RESOLVED;
conformance 2832/2832, fhirpath tree 1809 passed:

- **QA-001 (HIGH): fallback `parse_value` None-sentinel leak.**
  `fhir4ds/fhirpath/engine/util.py::parse_value` returned
  `parse_complex_value`'s None directly for Quantity-typed ResourceNodes /
  Quantity-shaped dicts lacking a usable unit/code, so `equality()` compared
  None==None → True: `{'value':120} = {'value':80}` (through children()
  traversal) was True in the fallback, false natively, and
  `repeat(children()).count()` diverged from `descendants().count()` (§5.8.2
  shorthand broken by over-dedup). Fix: fall through to the original value
  when the parse yields None. LESSON: when a spec defines one function as a
  shorthand of another (descendants ≡ repeat(children())), probe the
  equivalence — it surfaces deep equality/dedup bugs as countable
  divergences invisible at the top level.
- **QA-002 (MEDIUM): exported helper module gained children/descendants/
  trace** (`fhir4ds/fhirpath/duckdb/functions/navigation.py`, 8th instance
  of the "exported helper API forgotten" family; now/today/timeOfDay already
  existed in DateTimeFunctions). children() preserves null children and key
  order, reduces per item on collection input (engine parity), skips
  resourceType/underscore props, and raises FHIRPathError on unsupported
  types; descendants() = repeat(children()) with `=`-dedup delegating
  Quantity dicts to engine FP_Quantity equality (no duplicated conversion
  tables — REV-002 drift guard); trace() logs via logging, passes through,
  requires a non-empty string name.
- Verified clean (do not "fix"): null-child preservation in both engines;
  now/today/timeOfDay determinism (`= self` true), types, precision shapes
  (second-precision DateTime with ±HH:MM offset, day-precision Date,
  millisecond Time), `now() > @2020` true, Date-vs-DateTime comparisons
  empty; trace projection scope restoration and error-path pass-through;
  is_valid parity (single-argument `fhirpath_is_valid(expr)` form — the
  2-arg call is a Binder error).

### FHIRPath FP-12 HISTORIAN fixes (2026-08-17): children() model typing parity

Second personality on §5.8/§5.9. All 4 issues RESOLVED; conformance 2832/2832,
fhirpath tree 1822, tree-utility parity 20/20.

- **children()/descendants() must carry direct-navigation typing (§5.8.1).**
  Native `fn_children` (evaluator.cpp) now sets `field_name` + `fhir_type`
  via `infer_fhir_type` on every child, so §6.3 type operators
  (`ofType`/`is`/`as`) on children() agree with direct field access and the
  Python fallback (extension rebuilt + redeployed). Fallback counterpart fix:
  `create_reduce_children`'s choice-suffix propName rewrite previously used
  `res.propName` (None at the resource root), emitting malformed
  `None.multipleBirth` propNames that defeated
  `_matches_unqualified_choice_primitive` — `children().ofType(Integer/
  Boolean)` returned 0 while direct navigation matched. It now falls back to
  `res.path`, so `propName + typeSuffix` resolves through
  FHIR_PATH_TO_TYPE. AUDIT RULE: whenever touching children/descendants
  typing, probe the INTERNAL consistency anchor — `children().ofType(T)` vs
  `field.ofType(T)` within EACH engine; a same-engine divergence is
  unambiguous evidence of which side is wrong.
- **toString() of a preserved null child is empty (§5.5.2)** —
  `misc.to_string` gained the None branch; never let the Python None repr
  leak through conversion functions.
- **Nested-array JSON (array inside array) children are the elements** —
  `create_reduce_children` list branch appends elements directly (native
  fn_children parity) instead of building an index-keyed dict whose int keys
  crash `prop.startswith('_')`. Invalid-FHIR-but-valid-JSON inputs must
  degrade, not crash, at every tree-navigation boundary.
- Resume/interruption lesson: when a launch is interrupted mid-FIX, compare
  artifact mtimes (source, rebuilt extension, handoffs) against the state
  file before re-fixing — fixes may have already landed without bookkeeping.

### FHIRPath FP-12 EXPLORER fixes (2026-08-17): nested-path typing parity

Third personality on §5.8/§5.9 (123 fresh dual-path cases,
`/mnt/d/fhir4ds/.temp/qa/fp12_explorer3_2026_08_17/probe{,2,3}.py`). Chunk
closed (SKEPTIC 2, HISTORIAN 4, EXPLORER 2 fixes). Conformance 2832/2832,
fhirpath tree 1824.

- **Metadata-keyed typing fails on recursive paths by construction**
  (QA-001, HIGH). `Questionnaire.item.item.type()` → 'object' and
  `component.valueCodeableConcept.coding.ofType(FHIR.Coding)` → 0 in the
  Python fallback because path2Type/FHIR_PATH_TO_TYPE enumerate only finite
  path depths and choice-suffixed nested paths. Fix: `ResourceNode.
  _FIELD_NAME_COMPLEX_TYPES` (name/address/identifier/telecom/coding/code/
  extension/modifierExtension → HumanName/Address/Identifier/ContactPoint/
  Coding/CodeableConcept/Extension) + `_BACKBONE_ELEMENT_FIELDS`
  {communication, component, compose, contact, expansion, item, link} applied
  in `get_type_info` as the final Mapping fallback — mirroring the native
  `structuralFHIRComplexType` + field-name chains in evaluator.cpp. LOCKSTEP
  RULE: keep the nodes.py tables and the native chains aligned (REV-002
  drift family). Also added `".type": "code"` to
  `models/r4/fhir_path_to_type.json` (native `fhirFieldType` already had
  type→code); Questionnaire.item.type is FHIR.code, so
  `descendants().ofType(FHIR.string)` counts only `text` values.
- **extension/modifierExtension elements must type as FHIR.Extension**
  (QA-002, MEDIUM). Native field-name inference chains (fn_type, is/ofType,
  structuralFHIRComplexType) had no extension entry, so
  `extension.ofType(FHIR.Extension)` → 0 while `is(FHIR.Extension)` worked;
  the fallback special-cases childPath "Extension". Added at all three
  native sites; extension rebuilt + redeployed (repo bundle, site-packages,
  ~/.duckdb caches, md5 0b8cf9e5…).
- Verified clean (do not "fix"): `.sum()`-style unknown-function chains
  still diverge by the documented FP-02 EXPLORER QA-004 LOW doctrine
  (native continues with empty; fallback errors the expression); trace()
  with defineVariable projections, nested traces, empty-name logging;
  now()/today()/timeOfDay() arithmetic chains ((now()+1 year) > today());
  wide-tree equal-subtree dedup (60 identical generalPractitioner → 122
  descendants); `_primitive` companion Element children counts.
- QA probe doctrine addition: when a typing divergence appears, probe the
  SAME value shape through a metadata-covered path (control anchor) in both
  engines before filing — it pins which engine is wrong.

### FHIRPath FP-13 spec-compliance HISTORIAN launch (2026-08-17): §6.1 Equality

Second personality on §6.1 (~180 fresh dual-path cases in
`/mnt/d/fhir4ds/.temp/qa/fp13_historian_2026_08_17/`). One MEDIUM fixed:

- **Fixed: string `~` whitespace class (QA-001, MEDIUM).** §6.1.2 String
  Equivalence normalizes whitespace "as defined in the Whitespace lexical
  category" (§Lexical Structure), which is ONLY tab (U+0009), LF (U+000A),
  CR (U+000D) and space (U+0020). Native `normalizeEquivalentString`
  (evaluator.cpp) admitted the full Unicode whitespace set (U+0085, U+00A0,
  U+1680, U+2000–U+200A, U+2028/9, U+202F, U+205F, U+3000) so
  `'a b' ~ 'a b'` (NBSP) was true in BOTH engines; Python
  `normalize_string` used `str.isspace()`, which additionally admits
  U+001C–U+001F — a native-vs-fallback parity break. Both engines now use
  the 4-codepoint set (`_FHIRPATH_WHITESPACE` in
  `fhir4ds/fhirpath/engine/invocations/equality.py`; predicate in
  `normalizeEquivalentString`). Extension rebuilt + redeployed (repo
  bundle, /tmp/duckdb_cpp_ext, site-packages, md5 26937fe5…). Regression:
  `test_string_equivalence_whitespace_lexical_category_parity_fp13_historian`
  (21 cases) in `test_comparison_parity.py`. Lesson: resolve spec
  cross-references — "whitespace as defined in the Whitespace lexical
  category" only yields the bug after reading the category definition.
- **Verified clean (do not "fix"):** the spec's own §6.1 verbatim example
  blocks — DateTime timezone-offset equality (`= @2017-11-05T00:30:00.0-05:00`
  true, +00:00=-00:00=Z) and Date/Time precision equality (`=` EMPTY vs `~`
  false on differing precision); multi-item `=` order-DEPENDENT vs `~`
  order-INDEPENDENT incl. complex HumanName recursion (case-fold only under
  `~`); decimal `=` trailing zeros; §5.5 conversion-table type mixing
  (Boolean=1 EMPTY, 1='1' EMPTY, 5='5 cm' EMPTY, 5 '1' = 5 true);
  `1 year = 1 'a'` EMPTY (FP-01 fixture doctrine) and `1 second = 1 's'`
  true; Date-vs-String coercion true (FP-01 JSON-convenience doctrine);
  integer literals > 2^31-1 → empty (FP-06 doctrine); SKEPTIC
  least-precision decimal `~` fix regression-free at all four sites.
- Probe traps: union `|` dedups with `=` BEFORE `~` sees the collection —
  `(1.0 | 1)` collapses to one item; write multi-item `~` expectations with
  pairwise-distinct values. Also re-check probe harness `EMPTY` comparison
  case-folding before reading "SPEC-FAIL" lists.
- SKEPTIC's ARCH-001 shared decimal-equivalence helper remains DEFERRED;
  this launch touched evaluator.cpp in a different area (string
  normalization, single site — no duplication introduced).

### FHIRPath FP-13 spec-compliance SKEPTIC launch (2026-08-17): §6.1 Equality

- **Fixed: native decimal `~` least-precision rounding (QA-001, HIGH).**
  §6.1.2 requires rounding to the precision of the LEAST precise operand
  (trailing zeros ignored, so `1.0` has precision 0). Four native sites
  computed `cmp_prec = min` only when BOTH precisions > 0, else `max` —
  so whenever one operand was integral the MORE precise operand governed:
  native `1.0 ~ 1.0001` // false, `1 ~ 1.4` // false, `0 ~ 0.4` // false,
  `1.0 ~ 1.06` // false — while the Python fallback (`equality.py::
  is_equivalent`, always `min`, rounds at precision 0) returned true.
  Fixed all four sites to `min` with rounding applied at precision 0
  (evalBinaryOp singleton source_text path; singleton double fallback now
  via `decimalPlacesFromNumberText`; the multi-item `valuesEquivalentState`
  lambda; `jsonNumbersEquivalent`). Extension rebuilt + redeployed.
  Regression: `test_decimal_equivalence_least_precision_parity_fp13_skeptic`
  in `test_comparison_parity.py` (14 native+fallback cases).
- **Verified clean across both engines (do not "fix"):** `~` string
  semantics (per-whitespace-char normalization, no collapsing — `'a  b' ~
  'a b'` false; casefold), temporal equivalence (different precision →
  false not empty, incl. `@2012-01 ~ @2012` false, Date-vs-DateTime false,
  seconds/ms single decimal precision), empty propagation (`{} ~ {}` true,
  `{} = 1` empty, `{} !~ 1` true), incompatible types (`=` empty, `~`
  false), order-independent multi-item equivalence with length check,
  quantity tolerance half-width (max of operand half-widths = least
  precision), `23 ~ 23 '1'`, year↔month conversion equivalence, all
  official R4 testEquivalent/testNotEquivalent/testNEquality fixture
  semantics, and the FP-01 mixed calendar/UCUM year/month pins.
- **Re-verified pinned doctrine (QA-002, LOW INTENDED):** `23 'Cel' ~
  73.4 '[degF]'` stays EMPTY in both engines per the FP-13 HISTORIAN
  offset-temperature guard (affine UCUM conversion unimplemented by
  design; the N1 spec example claiming true is outranked by the wrong-
  result risk documented 2026-06-29). `!~`/`!=` are EMPTY consistently.
- **Structural (ARCH-001, LOW DEFERRED):** the decimal-equivalence
  precision rule lives in FOUR native sites; the duplication is why the
  first fix attempt patched non-executing sites. Extract a shared helper
  next time this area of evaluator.cpp is touched. Lesson: when fixing a
  native binary-operator semantic, grep for ALL dispatch sites of the
  operator string (singleton path vs multi-item lambda can duplicate the
  logic) and verify behavior through a rebuilt, redeployed, cache-cleared
  extension before declaring the fix landed.

### FHIRPath FP-13 EXPLORER §6.1 audit (2026-08-17, spec-compliance campaign)

Third personality on §6.1 Equality (133 fresh dual-path probe cases in
`/mnt/d/fhir4ds/.temp/qa/fp13_explorer3_2026_08_17/`). Two HIGH fixes, both
native-only (fallback already correct; extension rebuilt + redeployed,
md5 bfd0ac84…):

- **QA-001 (HIGH, FIXED): native Quantity `~` tolerance used
  trailing-zero-preserving precision.** §6.1.2 quantity-equivalence tolerance
  is the half-width of the LEAST precise operand with trailing zeros ignored
  (`1.0 'g'` has precision 0 → half-width 0.5), so `1.0 'g' ~ 1.06 'g'` is
  TRUE — native said false while the fallback (equality.py `decimal_places`
  rstrips '0') said true. Root cause: `countDecimalPlaces` (which correctly
  preserves trailing zeros for lowBoundary/highBoundary authored precision)
  was reused at both `quantityEquivalentState` tolerance sites. Fix: new
  `leastPrecisionDecimalPlaces()` (built on `decimalPlacesFromNumberText`) at
  both sites. Regression:
  `test_comparison_parity.py::test_quantity_equivalence_least_precision_parity_fp13_explorer`
  (16 dual-path cases). AUDIT RULE: when a spec precision rule is fixed in
  one native dispatch family (plain decimals — SKEPTIC), grep every OTHER
  family computing the same rule (quantities, JSON numbers) before closing
  the chunk.
- **QA-002 (HIGH, FIXED): `jsonNumbersEquivalent` merged JSON integers
  beyond 2^53.** It compared `round(double*scale)`; binary64 cannot
  represent 2^53+1, so `9007199254740992 ~ 9007199254740993` was TRUE
  natively while `=` was correctly false. Fix: exact `yyjson_get_sint`
  comparison when both JSON numbers are integers (cmp_prec is 0 there —
  precision-0 rounding is the identity for integers); real-valued pairs keep
  the double path. Found by running the FULL fhirpath pytest tree during fix
  verification (test_equality_parity.py large-JSON-numbers), not by the §6.1
  probe battery. Also updated that test's stale NBSP expectation to the
  FP-13 HISTORIAN whitespace doctrine (NBSP not normalized; both engines
  agreed, only the test was stale).
- **QA-003 (LOW, INTENDED): `1 'cm' ~ 1 's'` → EMPTY in both engines.**
  Dimensional-incomparability follows the campaign-wide incomparable-quantity
  empty doctrine (offset temperatures, incompatible dimensions) for `=` and
  `~` alike; no fixture pins dimensional-mismatch `~`. Do not "fix" to false.
- Verified clean (do not "fix"): union `|` dedups via `=` at construction
  (probe multi-item expectations must use pairwise-distinct values — the
  HISTORIAN trap reconfirmed); `given = 'John'` on a 2-element collection is
  false (§6.1 count mismatch); iif with empty criterion takes the else
  branch; `{} != {}` empty (§6 pinned); trailing-zero fractional seconds
  equal (`@T00:00:00.0 ~ @T00:00:00.00` true — trailing zeros ignored for
  temporal precision too); Z/+00:00/-00:00 all equal; exponent quantity
  literals (`1e9 'mg'`) evaluate empty in both engines.
- Chunk tally FP-13: SKEPTIC 1 HIGH + 1 INTENDED + 1 DEFERRED (shared
  decimal-equivalence helper — now widened to include the integer-exact
  branch), HISTORIAN 1 MEDIUM, EXPLORER 2 HIGH + 1 INTENDED. Conformance
  2832/2832 held throughout.

### FHIRPath FP-14 spec-compliance SKEPTIC audit (2026-08-18): §6.2 Ordering

Fresh dual-path audit of < <= > >= (64 adversarial cases + the FULL official
R4 fixture batch testLessThan/testLessOrEqual/testGreaterThan/
testGreaterOrEqual, 81/81 correct in BOTH engines; probes in
/mnt/d/fhir4ds/.temp/qa/fp14_skeptic_2026_08_18/). The ENGINE surfaces are
§6.2-compliant: string ordering is Unicode code-point lexicographic (emoji
U+1F600 > U+FFFD, not UTF-16 order), temporal ordering is offset-aware
instant semantics when both operands carry offsets (Z = +00:00 = -00:00),
precision-mismatch ordering and Date-vs-DateTime are empty (fixtures
testLessThan23-25), trailing-zero fractional seconds add no precision
(testLessThan26/27 → false), Boolean operands error→empty, Integer/Decimal
ordering is exact at 28 significant digits, quantity ordering is STRICT
(no §6.1.2-style tolerance) and rides the FP-01/FP-02 conversion surfaces,
empty propagates in both operand positions, and 29-digit Integer literals
stay empty (FP-06 doctrine). Three defects, ALL in the exported helper
module `fhir4ds/fhirpath/duckdb/functions/datetime.py` (9th instance of the
"exported helper API forgotten" family), ALL RESOLVED Python-only (engines
untouched; no extension rebuild):

- QA-001 (MEDIUM): `DateTimeComparisons` returned definitive booleans for
  precision-mismatched temporal ordering (spec/fixtures: empty). QA-002
  (MEDIUM): ordering ignored timezone offsets (naive local compare) and
  `equals` said Z != +00:00. Fix: all `DateTimeComparisons` ordering +
  equals now DELEGATE to the canonical engine `FP_Date/FP_DateTime/
  FP_Time.compare()` via lexical round-trip — the delegate-to-engine
  pattern recommended for the REV-002 helper-drift family. QA-003 (LOW):
  `DateTimeLiteral` TIME/DATETIME patterns required exactly 3 fractional
  digits; now 1–9 with scale-aware microsecond conversion (fixtures use
  '.0'). Stale unit pin `equals(@2019, @2019-06-15) is False` corrected to
  None (precision-uncertain equality is empty, per §6.1/§6.2 and both
  engines). Regression:
  `test_datetime.py::test_ordering_spec_semantics_fp14_skeptic` and
  `::test_fractional_seconds_one_digit_parse_fp14_skeptic`.
- ARCH residual (LOW, documented): the FHIRDate/FHIRDateTime/FHIRTime
  dataclass dunders still encode compare-at-min-precision semantics; they
  are off the public comparison path now — fold into the eventual
  helper-to-engine delegation cleanup (REV-002 family).
- Probe traps: fhirpath() returns lists of strings (compare ['true'] not
  'true'); official fixture XML is namespaced + primitive-attrib shaped —
  strip namespaces and unwrap `<x value="v"/>` to scalars before casting
  ?::JSON, or every fixture probe fails with ConversionException.

### FHIRPath FP-14 HISTORIAN ordering audit (2026-08-18, spec-compliance campaign)

Second personality on §6.2 Comparison (< <= > >=). Three issues fixed, one
deferred:

- QA-001 (HIGH, RESOLVED — native engine): `compareDateTimes` in
  `extensions/fhirpath/src/fhirpath/evaluator.cpp` compared fractional
  seconds through the 3-digit-truncated `millisecond` int while the Python
  fallback compares full precision — `@2018-03-01T10:30:00.1234 <
  @2018-03-01T10:30:00.1236` was false natively / true in fallback, and
  `=` said true natively. §6.2: seconds+fractions are "a single precision
  using a decimal, with decimal comparison semantics". Fix:
  `DateTimeParts.frac_digits` (untruncated, populated in BOTH parsers
  before ms padding) + field loop capped at whole seconds + decimal
  fraction compare (right-pad to equal width, digit-lexicographic —
  trailing-zero-insensitive). Extension rebuilt AND redeployed (repo bundle
  + site-packages). Regression:
  `test_comparison_parity.py::test_subsecond_decimal_comparison_parity_fp14_historian`
  (19 dual-engine cases). Doctrine: when one engine stores temporal
  sub-seconds as a millisecond int and the other as a float/microsecond
  timestamp, probe 4+ fractional digits — official fixtures never do.
- QA-002 (MEDIUM, RESOLVED — exported helper, 10th "exported helper API
  forgotten" instance): `DateTimeComparisons` Time-vs-Date/DateTime
  ordering returned definitive booleans. The §5.5 implicit-conversion
  table defines no Time<->Date/DateTime conversion, so ordering across
  those types is empty; `_engine_compare` now type-guards to None.
- QA-003 (MEDIUM, RESOLVED — exported helper): `_engine_compare` crashed
  with AttributeError when an FP temporal constructor returned None
  (`FHIRDate.from_string('2018-03-01+05:00')` over-accepts offsets).
  None-guard added: invalid lexical operand -> None (empty). Residual
  (LOW): the over-accepting `parse_date` itself is a parse-layer issue
  left for a parse chunk.
- QA-004 (LOW, UNCONFIRMED/DEFERRED): `@2018-03-02 > @2018-03-01T12:00`
  is true in both engines (definitive at shared coarser precision despite
  differing precision levels). Spec prose is self-conflicting (unconditional
  precision-mismatch-empty vs first-difference walk; implicit
  Date->DateTime conversion exists), no fixture covers Date-vs-DateTime
  ordering, and both engines agree — needs a spec/human anchor before any
  change. Do not "fix" without one.
- Verified clean both engines (new ground beyond SKEPTIC): multi-item
  operands `(1|2) < 2` empty; type-mismatch `5 < '5'`, `true < 1`,
  `@T12:00:00 < @2014-01-01` empty; spec §6.1/§6.2 timezone-conversion
  examples (`-04:00` vs `-05:00` all four operators); one-sided offsets
  (parity, implementation decision per spec); `1 year > 1 'a'` empty /
  `10 seconds > 1 's'` true / `1 'min' > 61 's'` false; chained
  `1 < 2 < 3` empty; SKEPTIC's 3 fixes re-verified regression-free.
- Validation: focused 178/178, fhirpath tree 1896 passed, conformance
  2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47). Probe:
  `.temp/qa/fp14_historian_2026_08_18/`.

### FHIRPath FP-14 EXPLORER fixes (2026-08-18): §6.2 chunk closed

Third personality on §6.2 Comparison (23-case focused probe + reuse of the
82-case interrupted battery; `.temp/qa/fp14_explorer2_2026_08_18/`). Three
Python-fallback fixes (native already correct — FP-14 HISTORIAN frac_digits;
NO extension rebuild), all in `fhir4ds/fhirpath/engine/nodes.py`:

- **QA-001 (HIGH): fallback sub-microsecond temporal ordering/equality.**
  `FP_TimeBase.compare()`/`equals()` equal-precision branches compared
  `_getDateTimeInt()` built from a dateutil `timestamp()`, which truncates
  fractional seconds at microseconds — `@...:00.1234567 <
  @...:00.1234568` was false and `=` true. Now: componentwise walk of the
  tz-normalized lists plus exact decimal compare of the raw fraction digit
  strings (`_fraction_digits()` + `_compare_decimal_fractions()`: missing
  fraction = "0", right-pad, trailing zeros add no precision per fixtures
  testLessThan26/27).
- **QA-002 (HIGH): FP_Time 7-9 digit fractions never built a time object.**
  `strptime("%f")` caps at 6 digits, so `_pyTimeObject` stayed None and ALL
  ordering errored to empty (even `.999999999 < next second`). Manual
  time-object fallback added (µs-truncated object backs display/arithmetic
  only; ordering uses digit strings).
- **QA-003 (MEDIUM): equal-precision Date-vs-DateTime ordering mixed
  incommensurate numeric scales** — FP_Date multiplier-sum ints (~6.4e10)
  vs FP_DateTime epoch timestamps (~1.45e9) — so `@2015-01-01 <
  '2016-01-01'.toDateTime()` was false while the literal-vs-literal and
  reversed-operand forms were true. The componentwise rewrite removes the
  scale mix.
- Regression: `test_comparison_parity.py::
  test_subsecond_and_cross_type_comparison_parity_fp14_explorer` (13
  dual-path cases). Validation: parity file 107, fhirpath tree 1909,
  conformance 2832/2832.
- ARCH-001 (LOW, DEFERRED): `engine/invocations/collections.py` orderBy
  helpers still use `_getDateTimeInt()` and inherit the same scale-mix /
  µs-truncation family — outside §6.2 scope, flagged for a future
  collections-ordering chunk.
- Chunk tally FP-14: SKEPTIC 3 helper fixes, HISTORIAN 3 fixes + 1 LOW
  UNCONFIRMED (Date-vs-DateTime definitive ordering, deferred to human),
  EXPLORER 3 fallback-engine fixes + 1 ARCH LOW deferred. Chunk CLOSED.
- Probe-harness lessons: fhirpath() outputs are LISTS of strings — compare
  `['true']`, never `'true'` (the interrupted launch's 71 phantom
  "spec-diff"s were all this artifact); and verify probe-comment UTC
  arithmetic before encoding expectations (`00:00+14:00` is
  `2019-12-31T10:00Z`, NOT the same instant as `12:00-12:00`).

## Milestone code review #3 (2026-08-18, FP-11..FP-15 delta)

Line-by-line review of the uncommitted campaign delta since review #2 is in
`fhir4ds-private/docs/prompts/.ai_loop/code_review_findings.md`. No
CRITICAL/HIGH findings and NO new issues at all in this delta; validated with
math/comparison/type parity (156 passed) and helper unit tests (362 passed).
All five prior findings remain OPEN hardening/debt items: REV-001 LOW
(`std::stoi("-")` still reachable in `fhirpathSplitUnitTerm` for terms ending
`-`; hardening only), REV-002 MEDIUM (metadata duplication widened again by
FP-15: typecheck.py System-name list + nodes.py field-name type tables mirror
native chains; generate from models/r4 when next touched), REV-003 LOW
(unrelated untracked files still in the tree; stage campaign files
explicitly), REV-004 LOW (no 128-bit budget guard in `exactDecimalRatioText`),
REV-005 LOW (mid-pattern inline regex flags still DeprecationWarning on the
Python path). Bundled extension binary (11:05) verified newer than the last
evaluator.cpp edit (10:59).

## FHIRPath §6.5 Boolean Logic — FP-17 EXPLORER launch (2026-08-18, spec-compliance campaign)

Third personality on §6.5 (probes: `.temp/qa/fp17_explorer/probe_core.py`,
`.temp/qa/fp17_explorer/probe_db.py`). Explored toBoolean-convertible operands
(0, 1, 0.0, 'true'/'false'/'1'/'0' strings), empty operands from
where()/exists() projections, iif-produced operands, nested trees mixing all
five operators, comparison-with-empty-side chains — across core engine, native
C++ extension, and forced Python fallback. 0 parity diffs.

- **DO NOT "FIX" truthy singleton Boolean evaluation for §6.5 operands.** The
  QA hypothesis that toBoolean conversion criteria apply to and/or/xor/implies/
  not() operands (so `0 and true` → false) is WRONG. Official R4 fixtures
  `testLiterals/testIntegerBooleanNotTrue` (`(0).not() = false` → true) and
  `testIntegerBooleanNotFalse` (`(1).not() = false` → true) mandate that every
  non-Boolean single node (including 0, 1.0, 'false') evaluates to TRUE in
  Singleton Evaluation of Collections for boolean logic. A conversion-based
  "fix" was implemented, failed the official fixture (934/935), and was fully
  reverted per the Recovery Gate. NOT A BUG — see the pin tests
  `test_boolean_operators_treat_non_boolean_singletons_as_truthy` (core +
  dual-path parity) and `test_not_treats_non_boolean_singletons_as_truthy`.
- Consequence pin: `true implies 'false'` = true; `'false' implies false` =
  false; `'false'.not()` = false; `0.not()` = false — all three engines agree.
- Environment: `git checkout` on this repo can take minutes under WSL2; stale
  `.git/index.lock` may need manual removal after interrupted git commands.

### FHIRPath §6.6 Math / §6.7 Date-Time Arithmetic — FP-18 SKEPTIC launch (2026-08-18, spec-compliance campaign)

**Fixed in FP-18 SKEPTIC iter 1 (2026-08-18).** DOCTRINE: `div`/`mod`
(§6.6.5/§6.6.6) must use EXACT truncated division — never `int(x / y)`,
`int(dx / dy)`, `std::trunc(double)`, or `std::fmod` mediators, which silently
round operands beyond 2^53 (`9223372036854775807L div 1` → …808). Python:
exact int truncation (`//` adjusted toward zero) and `Decimal //` (Decimal
floordiv truncates toward zero, exact). Native evaluator.cpp: exact int64
div/mod for Integer-typed operands (Integer + Long literals), returning
`FromInteger` so 64-bit quotients never render scientific notation (§5.5.8);
int64 div overflow (LLONG_MIN div -1) → empty on BOTH engines (mirrors the
divide-by-zero convention; avoids a new coupled error message).

**DOCTRINE: exact Decimal `mod` in the native engine.**
`tryDecimalModExactText` (evaluator.cpp): __int128 decimal-text truncated mod
from operand source_text with aligned exponents and checked scaling, bails to
binary64 fmod on overflow — `0.10000000000000000000000000001 mod 0.1` must
return the exact 29-digit remainder, not fmod's 0.0.

**DOCTRINE: literal ranges.** Unsuffixed Integer literals beyond 32-bit
(±2^31) raise "Integer literal out of range" in the strict core (lockstep
with native; N1 §22.1) — large whole numbers need `.0` (Decimal) or `L`
(Long, int64 range; literal 2^63 is allowed only because unary minus maps it
to LLONG_MIN, mirroring native's special case).

**Error-message contract (13th instance of the recurring family):** the
div/mod Quantity/Boolean "Cannot … div/mod …" messages, the three
" For date/time arithmetic," unit-error prefixes, and the
`_evaluate_literal_temporal_arithmetic` ValueError leak were added/fixed in
`_is_valid_empty_result_error` + `_evaluate_literal_temporal_arithmetic`
(udf.py) so `fhirpath_is_valid` stays in lockstep with the native engine's
empty-result semantics. New execution-error messages MUST be added to the
acceptance lists before a chunk closes.

**Known DEFERRED divergence (FP-18 QA-006):** native `/` renders
shortest-round-trip 16-digit text while the fallback renders Python Decimal
28-significant-digit text (`1 / 3`); numeric values agree and no fixture pins
the rendering. Fixing requires porting decimal-context division to C++.

**NOT A BUG pins:** dateTime − dateTime and Time − Time are NOT defined
(§6.7.2 right operand must be a Quantity) → error/empty, correct. `&`
converts singleton non-string operands via toString and treats {} as the
empty string (fixtures testConcatenate1–3). Date+hours / Time+days /
`+ 1 'a'` are §6.7.1 unit violations → execution error (valid expression,
empty at UDF). Mod remainder sign follows the dividend (truncated division):
`-5 mod 2 = -1`, `5 mod -2 = 1`.

**FP-18 launch environmental note (QA-007, HIGH DEFERRED):** the campaign
working tree has a pre-existing source/binary/test three-way drift in
integration parity suites: 183 `fhir4ds/fhirpath/duckdb/tests/integration/`
failures (FP-02 quantity-arithmetic examples, FP-11 sqrt/power rendering,
FP-12/15 typing) reproduce identically with the pre-FP-18 binary — the
ARCHIVE_LOG-described FP-11 helpers (`expandScientificToFixed`/
`shortestRoundTripText`) are absent from evaluator.cpp at HEAD and in the
tree. The conformance master gate (2832/2832) is unaffected. Any C++
rebuild re-flows this drift into deployed binaries; schedule a
reconciliation chunk before further C++ work.

### FHIRPath §6.6/§6.7 Math + Date/Time Arithmetic — FP-18 EXPLORER launch (2026-08-18, spec-compliance campaign)

91-case dual-path boundary-combination probe (`.temp/qa/fp18_explorer3_2026_08/probe.py`),
verified against FHIRPath N1 §6.6/§6.7 normative text (spec/N1/index.adoc from
github.com/HL7/FHIRPath) + R4 fixtures. Verified clean on BOTH engines: `&`
empty-as-empty-string chains at depth incl. mixed implicit toString of
int/Decimal/bool/Quantity/date/Time/dateTime; arithmetic feeding comparisons
feeding and/or/implies/iif; div/mod sign matrix (negatives, exact multiples,
Decimal divisors, zero divisors → empty); Long binary arithmetic at int64
bounds (overflow → Decimal, doctrine); §6.7 month-end clamping (Jan31+1mo→Feb29,
Feb29+1yr→Feb28, Dec31+2mo→Feb28 — matches the N1 ISO8601 table exactly);
fractional-quantity truncation; Time ± quantities at all precisions incl.
midnight wrap/underflow and hour-precision no-op; dateTime−dateTime /
date−date consistently empty (no §6.7.2 difference operator in N1);
arithmetic inside where/select/repeat with `$this`; unary minus chains.

Fixed (2 RESOLVED, extension rebuilt + redeployed, conformance 2832/2832):
- **QA-001 MEDIUM — unary-minus Long overflow parity (§6.6 overflow doctrine):**
  `- -9223372036854775808L` native→empty, core/fallback→raw Python int 2^63
  (out-of-domain). Core `polarity_expression` now degrades int negation
  outside int64 to exact Decimal (mirrors `_numeric_arithmetic_result`);
  native `evalUnaryOp` LLONG_MIN branch returns Decimal
  `9223372036854775808.0` (source_text-pinned) instead of empty.
- **QA-002 MEDIUM — `&` implicit conversion of complex JSON values (§6.6.7):**
  `qs & ''` fallback emitted Python dict repr (`{'value': 3, ...}`) vs native
  compact JSON. `math.amp._string_value` now serializes dict/list values via
  `json.dumps(separators=(",",":"), ensure_ascii=False)`. Python-only.

NOT A BUG registry (QA-003, LOW INTENDED): unary-minus Integer overflow
renders Long-style (`- -2147483648` → `2147483648`, no `.0`) while binary
`2147483647 + 1` degrades to Decimal (`2147483648.0`); both engines behave
IDENTICALLY, no fixture pins the unary rendering; left as-is to avoid churn.
Harness trap (repeat): `fhirpath_text` returns the FIRST item of multi-item
results — probe multi-item expectations via `fhirpath()` JSON lists, else the
harness manufactures phantom failures.

### FHIRPath §7 Aggregates + §8 Lexical Elements — FP-19 SKEPTIC launch (2026-08-18, spec-compliance campaign)

NOT A BUG pins (verified against tests-fhir-r4.xml testAggregate1-4 and
FHIRPath.g4; do not "fix"):
- One-arg `aggregate(aggregator)` starts `$total` as the EMPTY collection, not
  the first element. `(1|2|3).aggregate($this+$total)` → empty is CORRECT; the
  fixture-canonical pattern is `iif($total.empty(), $this, ...)`. Empty input
  with init → init; empty input without init → empty.
- Block comments are NON-nested (`/* a /* b */ c */` is a syntax error after
  the first `*/`); unterminated block comments are syntax errors.
- `TRUE`/`True` are identifiers (→ empty), not booleans; keywords and function
  names are strictly case-sensitive (`Iif`, `Empty()`, `Abs()`, `SELECT()`,
  `DIV`, `Is`, `And` all rejected). Backtick delimited identifiers may be
  reserved keywords (`div`, `and`, `class`) and carry escapes.
- Heterogeneous `aggregate` errors (e.g. `(1|'a'|2).aggregate($this+$total,0)`)
  surface identically at the DuckDB UDF boundary (empty) even though the Python
  fallback raises internally — the UDF wrapper normalizes; parity contract is
  the UDF surface, not the raw engine exception.

DEFERRED (LOW): malformed string escapes (`\uZZ`, short `\u41`, `\q`)
silently drop the backslash in BOTH engines instead of strict ESC/UNICODE
grammar rejection. This is the documented FP-10 tolerant-STRING corner
(fhir4ds/fhirpath/parser/FHIRPath.g4 STRING comment). Revisit only if an
official fixture pins strict rejection.

FP-19 chunk verified clean: 55+ dual-engine probe cases, conformance 2832/2832,
no code changes required. Probe: .temp/qa/probe1..4.py.

### FP-19 HISTORIAN launch addendum (2026-08-18, spec-compliance campaign)

New territory verified clean, dual-engine (probes .temp/qa/fp19h/probe1..3.py);
no code changes. Additional NOT A BUG pins:
- `$index` inside an `aggregate()` aggregator is the 0-based index of the
  CURRENT item (`[10,20,30].aggregate($this+$total+$index,0)` → 63); init is
  evaluated once and may reference outer context
  (`a.aggregate($this+$total, a.count())` → 63). Chained/nested aggregates and
  the official §7 dedup example `iif($total contains $this, $total, $this|$total)`
  (→ [3,2,1]) conform in both engines.
- NUMBER lexical edges: `.5`, `1.`, `1 .5`, `1e3`, `3.5L` are syntax errors;
  `007` (→ 7), `0.0`, and `1L` (LONGNUMBER, integer + `L`, NO space — `1 L`
  invalid) are grammar-valid.
- `@2018Z` and `@T12:30Z` are rejected by both engines even though the
  FHIRPath.g4 DATETIME/TIMEFORMAT rules permit `Z` lexically: FHIR dateTime
  semantics forbid a timezone without time components and the FHIR time
  datatype has no timezone. This is the documented strict temporal policy
  (FP-06 invariant, CQL-11 note) — do not loosen.
- Quantity literals with UCUM units parse fully: `10 'cm/mmol'.unit` →
  `cm/mmol`; `10 'cm' = 100 'mm'` → true.
- Comment tokens are lexed AFTER string literals: `'http://not-a-comment'` and
  `'/* not comment */'` keep their contents; comments adjacent to numbers
  without whitespace (`1//c\n+2`) work.
- Non-ASCII identifiers (`café`) are token errors per grammar charset; empty
  and whitespace backtick identifiers are grammar-valid (eval empty);
  whitespace may surround `.` navigation (`a . count()`).

### FHIRPath §7/§8 — FP-19 EXPLORER launch (2026-08-18, spec-compliance campaign)

**Fixed (native evaluator.cpp; extension rebuilt + redeployed to repo bundle
and site-packages; ucum_units.hpp and CQL extension untouched):**
- **Incompatible-operand arithmetic must signal an error, not degrade to
  empty** (N1 §6.6 "the evaluation of the expression will end and signal an
  error"). Native `(1+'x') | 99` returned `['99']` while the fallback
  aborted to `[]`. evalBinaryOp now throws
  `Incompatible operands for arithmetic operator '<op>'`; the prefix is in
  the native `FhirpathIsValidFunction` acceptance list (execution
  type-error class, mirroring the fallback's accepted `"Cannot [..]"`
  messages). Regression:
  `test_incompatible_arithmetic_errors_abort_parents_fp19_explorer`.
- **Mixed-unit quantity +/- must return the most granular input unit**
  (N1 §6.6.3: `3 'm' + 3 'cm' // 303 'cm'`). Native returned the canonical
  base unit (`3.5 'wk' + 2 'd'` → `2289600 's'`). Now mirrors the fallback's
  `_quantity_add_or_sub` (smaller |factor-to-base| wins; ties prefer the
  canonical/base-form operand). Regression:
  `test_mixed_unit_quantity_sum_uses_most_granular_unit_fp19_explorer`.

**Discovered, deferred (pre-existing on the git-HEAD binary — not a
regression of this launch):** native lacks the derived/prefixed UCUM
families (`1 'kN' = 1000 'N'` → empty) and number±quantity arithmetic
(`2 + 2 '1'` → empty), so 86 integration-parity assertions fail natively
(test_arithmetic_parity.py 84; environment_type/existence parity 1 each).
NOTE: the FP-11 note above references a native
`FhirpathDerivedUnitTable()` — no such function exists in the current
evaluator.cpp (git -S finds no commit adding it); institutional memory
overstates native coverage. Fix requires a curated native table mirroring
`nodes.py::_UCUM_CONVERSIONS`, multi-term compound-unit reduction, a
number±quantity branch, and coordinated extension rebuilds.

**Parity test resource gotcha:** when a probe expression references a
collection field, the resource must actually contain it — a missing field
yields init-only aggregate results (`a.aggregate(...)` on resource without
`a` → `[0]`) that look like error-swallowing but are correct.

**Conformance after fixes:** run_all.py 2832/2832 (ViewDef 144, FHIRPath
935, CQL 1706, DQM 47); fhirpath unit suites 253 + 993 passed.

### Milestone review #4 + parity drift diagnosis (2026-08-19, code_review launch)

**Part B drift root cause identified: sibling-session whole-file clobbering.**
Current tree: 75 integration parity failures (was 183 pre-rebuild). Buckets:
~108 already fixed by the Aug 19 rebuilds (stale committed binary);
**67 = LOST SOURCE FIXES** — evaluator.cpp/operators.py were overwritten by
later sibling sessions without earlier chunks' hunks (FP-11
powerDecimalExactText/expandScientificToFixed/shortestRoundTripText exact
power & decimal text, FP-13 leastPrecisionDecimalPlaces equivalence, FP-15
`!explicit_namespace` literal-Quantity isType guard, FP-12
extension/modifierExtension fhirFieldType entries, FP-19 `(1+'x')|99`
error-abort, FP-16 operators.py membership/contains raise — its regression
test now FAILS); ~2 std::regex named-group native limitations; 6 untriaged
(temporal-edge fallback expectations, string equivalence parity).
Binary is fresh vs source and md5-matched to site-packages — staleness is
NOT the current issue; the source itself is deficient.
Reconciliation (see code_review_findings.md Part B): freeze concurrency,
re-land the six lost fixes (tests already define done), rebuild+redeploy,
xfail/triage the ~8 remainder, and add a post-build symbol grep as a clobber
guard. Do not commit the tree until steps 1-3 are done.
Operational rule: never run two campaign launches against the same working
tree without a single-writer lock; whole-file rewrites of evaluator.cpp
silently drop other sessions' hunks. (Note: evaluator.cpp contains a literal
NUL byte inside a comment — use `grep -a`.)

### FHIRPath milestone-4 reconciliation — lost-fix re-land (2026-08-19, bug_fix REV-006/REV-007)

Sibling-session whole-file clobbers of `evaluator.cpp`/`operators.py` had
dropped verified campaign fixes (review-20 Part B). After re-landing (most
families were already restored in the Aug 19 03:45 source; this pass added
the two genuinely missing residuals below), integration parity is
7 failed / 765 passed and conformance 2832/2832 holds. Known fragile areas,
refined:

- **`convertQuantityUnit` exact metric conversion (FP-08 EXPLORER QA-002,
  re-landed).** `decimalFactorRatio()` converts table factors to exact
  integer ratios via SHORTEST round-trip text. Two binary64 traps: (1)
  derive the from-factor via `convertQuantityToBase(1.0, unit)` — never
  `from_base_value/value` (quotient noise like 1000.0000000000001 silently
  defeats exact-ratio guards); (2) `%.1g` renders 1000 as "1e+03", so
  scientific integral forms must map to `den=1`. Pinned by
  `test_toquantity_metric_conversion_28_digit_decimal_parity_fp08_explorer`.
- **Unitless quantity JSON vs bare number equality is EMPTY (§6.1.1).**
  `jsonValuesEqualState` returns −1 for quantity-shaped objects without
  unit/code vs numbers (`{"value":120} = 120` → empty, not false; `1 '1' = 1`
  stays true). NOTE: `fpValueAsQuantity` rejects unitless objects, so this
  guard lives in the JSON comparator, not `valuesEqualState`. Pinned by
  `test_children_type_operators_match_direct_navigation_fp12_historian2`.
- **Clobber guard doctrine (process):** after ANY edit/rebuild of the two
  campaign-hot files, symbol-check before validating:
  `leastPrecisionDecimalPlaces`, `powerDecimalExactText`,
  `expandScientificToFixed`, `frac_digits`, `!explicit_namespace`,
  fhirFieldType extension entries, `decimalFactorRatio`, and the
  operators.py membership raise — grep needs `-a` on evaluator.cpp (benign
  NUL byte in a comment).
- Residual 7 parity failures: 2 std::regex named-group limits
  (`replaceMatches` `$1`) + 5 temporal-edge FALLBACK-side expectation
  mismatches (@2016 + 1 'a' family) — untriaged, next-chunk candidates.

## CQL-01 Primitive Types Launch (2026-08-19)

Spec-compliance launch CQL-01 (CQL 1.5 Any/Boolean/Integer/Decimal/String/
Long): 6 spec divergences fixed (runtime overflow null-guards, decimal
extent typing, ToDecimal/literal scale rounding, Truncate→Integer, CanConvert
lowering). Conformance gate held at 2832/2832. Durable discoveries recorded
in fhir4ds/cql/AGENTS.md: shared DuckDB macro names between the CQL and
FHIRPath macro packages must stay byte-identical (registration order
clobbers); DuckDB TRY() cannot wrap volatile functions including all Python
UDFs; decimal implementation scale is 8 fractional digits and over-precision
inputs are rounded half-up, never rejected. NOTE: 7 pre-existing
native-extension regex parity failures in fhirpath/duckdb pytest
(named-group/multiline replaceMatches) remain outside the conformance gate.

## CQL-03 Temporal/Complex Spec Launch (2026-08-19, SKEPTIC iter 1)

Spec-compliance launch CQL-03 (CQL 1.5 Types — Temporal and Complex: Date,
DateTime, Time, Quantity, Ratio). 2 HIGH fixed, 1 LOW INTENDED. Conformance
gate held at 2832/2832. Durable discoveries:

- **Strict temporal literal lexing (QA-001, HIGH, FIXED):**
  `fhir4ds/cql/parser/lexer.py:_validate_datetime_literal` now enforces the
  CQL 1.5 grammar shapes (zero-padded DATE/TIME/DATETIME, optional
  `Z|±hh:mm` offset) plus full calendar/leap-year validation via
  `datetime.date` and Time component range checks; malformed literals
  (`@2024-1-1`, `@2024-02-30`, `@2024-01-15.year`, offset `+02` without
  minutes) raise `LexerError` instead of lexing into garbage values. NOTE:
  compose regex patterns by string concatenation, NOT f-strings — f-strings
  mangle `{2}` quantifiers into replacement fields. Out-of-range offset
  VALUES (`+14:30`, `+99:00`) remain runtime-invalid (null), not lex errors,
  per the conformance doctrine pinned in test_datetime_part1_parity.py.
- **Same-code quantity comparison unit validity (QA-002, HIGH, FIXED):**
  `extensions/cql/src/cql/quantity.cpp:quantity_compare` same-code fast path
  now guards with `same_code_unit_valid_for_compare()`: a unit is valid when
  it is a table unit, a UCUM annotation (`{dose}`, `[pH]`), an annotated
  known unit (`mm[Hg]` → `mm`), or a compound of valid components
  (`mg/m2`). Genuinely unknown bare codes (`xyz`) → null (§Equal) / false
  (~Equivalent). WARNING: a table-only validity guard regressed 3 DQM
  measures (CMS69/CMS771/CMS1218 compare annotation/compound units) — any
  change to unit validity must be annotation/compound-aware and gated by the
  full DQM suite. Also: recursion into compound components must be guarded
  against separator-free self-recursion (caused a segfault in the first
  build). Extension rebuilt + md5-verified deployed (bundle +
  site-packages): 67c1b10a93db5cc47b26082dfc43de21.
- **NOT A BUG registry (QA-003, LOW INTENDED):** `ToString(1:8)` renders
  `1.0 '1':8.0 '1'` (trailing `.0`) while `ToString(5 'mg')` renders
  `5 'mg'`. Ratio components are Decimals and RatioToString preserves
  Decimal formatting, pinned by fhir4ds/cql/duckdb/tests/test_ratio_udfs.py
  (:301-313); both backends agree; CQL 1.5 §ToString examples never exercise
  whole-value Ratio formatting.

## CQL-04 Logical Operators Spec Launch (2026-08-20, SKEPTIC iter 1)

Chunk CQL-04 (CQL 1.5 And/Or/Not/Xor/Implies) SKEPTIC audit — dual-path
(macros + end-to-end population SQL, Python supplements vs C++ extension):

- **NOT A BUG Registry — Boolean define population-surface null collapse.**
  `translate_library_to_population_sql` reports a Boolean define that
  evaluates to CQL null as FALSE (final projection `CASE WHEN
  "Def".patient_id IS NOT NULL THEN TRUE ELSE FALSE`). This is intentional:
  measure population membership treats null criteria as not-in-population
  (null ≡ false for membership), and boolean define CTEs are row-presence
  based (`_wrap_expression_in_select`, cte_manager.py; referenced via EXISTS
  throughout the translator — do NOT add value columns to boolean CTEs
  without reworking every EXISTS reference). Expression-level 3VL is fully
  spec-correct: lowered SQL preserves SQL NULL (Kleene tables verified for
  all 9 operand combinations per operator). Pinning regression:
  `test_cql_logical_null_propagates_in_lowered_sql_and_collapses_to_false_at_population_surface`
  in `fhir4ds/cql/duckdb/tests/integration/test_logical_parity.py`.
- **Implies truth table note.** CQL 1.5 spec (Appendix B / Table 9-A1):
  null implies null → NULL (not true); null implies true → true;
  null implies false → null; false implies X → true. Both the "Implies"
  macro and the NOT A OR B lowering implement this correctly. Outer
  campaign prompt claiming "null implies null → true" is wrong vs spec.
- **Function-call forms And(a,b)/Or(a,b)/Xor(a,b)/Implies(a,b) are NOT CQL
  syntax** — ParseError is correct (CQL grammar: infix and/or/xor/implies,
  prefix not only). The quoted "And"/"Or"/"Xor"/"Implies"/"Not" DuckDB
  macros are internal lowering surfaces; `Not(x)` in CQL parses as unary
  `not (x)`.
- Non-Boolean operands (`1 and true`, `not 'yes'`, `1 + 1 and true`) raise
  TranslationError at translate time (CQL static Boolean typing) — verified.
- Precedence/chaining verified per spec (not > and > or/xor > implies,
  left-to-right within category) including `true implies false implies true`
  (left-assoc → true).

### CQL-04 EXPLORER (launch 3, 2026-08-20): `not` precedence direction corrected

- **CRITICAL grammar correction:** ANTLR left-recursive alternative order
  means EARLIER alternatives bind TIGHTER. In the official HL7/cql v1.5.3
  `cql.g4`, `#notExpression` is listed BEFORE between/set/inequality/
  timing/equality/membership/and/or/implies, so `not 5 in {1,2}` parses as
  `(not 5) in {1,2}` (a static type error), NOT `not (5 in ...)`. The
  CQL-04 HISTORIAN fix that moved `not`'s operand to the equality tier was
  based on a reversed precedence reading and was itself a spec regression
  (QA-001). `not` still binds LOOSER than `is [not] null/true/false` and
  `is`/`as` (`not X is null` = `not (X is null)`) and TIGHTER than
  and/or/xor/implies (`not true and false` = `(not true) and false`).
  Verified by generating an ANTLR 4.13.1 parser from the official grammar
  (`.temp/qa/cql04_explorer2_2026_08_20/prec_probe.py`).
- Multi-`when` case expressions with a LATER literal-true when collapsed to
  that branch, discarding earlier matching whens (QA-002,
  translator/expressions case lowering).
- Boolean define aliases materialize via `fhirpath_text` (VARCHAR) and leak
  string truthiness into and/or/not/xor (`F and true` all-true, `not F`
  all-false) (QA-003). Query-let aliases and direct inlining are correctly
  Boolean-typed.
- Verified correct: implies/xor left-associative chains, mixed precedence,
  absent-Boolean-field 3VL, Coalesce/is-null compositions, division and
  malformed-DateTime guards under and/or/implies (null-propagating, no
  eager SQL errors), tuple selectors, py-vs-cpp parity throughout.

**CQL-04 EXPLORER remediation status (same launch):** all three RESOLVED —
`not` precedence re-fixed per the corrected grammar reading
(parser.py `parse_not_operand`/`parse_equality_operand`); case first-match
tail fix in `_lists.py`; Boolean define aliases now contribute their VALUE
via `CAST((SELECT ...) AS BOOLEAN)` under BOOLEAN usage
(`_classify_definition_ref` returns CORRELATED_SCALAR for value-bearing
defines). Regression tests in `test_logical_parity.py`; conformance
2832/2832 held.

### CQL Structural Type Operators (chunk CQL-05, HISTORIAN 2026-08-20)

- Known fragile: query aliases bound to `as`-cast expression sources (e.g.
  `O.value as FHIR.Quantity Q where Q is FHIR.Quantity`) — the alias must bind to the
  cast VALUE per element; binding it to retrieve rows silently drops the cast (QA-101).
  See `_alias_is_element_value` in `fhir4ds/cql/translator/expressions/_query.py`.
- Known fragile: nested list literals inside list-literal arguments
  (`Descendants({1, {2, 3}})`); flattening is spec-required (QA-102).
- NOT A BUG registry: `convert 'yes'/'y'/'1' to Boolean` → True/False family is
  spec-correct per CQL 1.5 ToBoolean (true/t/yes/y/1, false/f/no/n/0, case-insensitive,
  else null); `convert true to Integer` → 1 is spec-correct (ToInteger Boolean overload);
  Quantity→String "1 'mg'" matches spec format.

### CQL-05 HISTORIAN launch addenda (2026-08-20)

- Architecture Drift Log: `_translate_query`'s CTE-flatten region accumulates per-shape special
  cases (union / placeholder / set-op / value-projection). New element-value query sources should
  converge on one alias-registration path (`add_alias(table_alias=alias)` + `_alias_source_asts`)
  and the `_alias_is_element_value` classifier instead of extending the elif chain.
- Invariant: element-value row projections must stay SINGLE-column — adding patient_id to a
  value-projection SELECT breaks scalar-subquery call sites (14 DQM binder errors observed).
- NOT A BUG additions: nested list literals in Children/Descendants serialize via json_array
  (DuckDB cannot type heterogeneous arrays); `Descendants({1, {2, 3}})` → [] is spec-correct.
- Process finding: parallel chunk launches share this working tree; a DQM gate regression
  (32/47, 2026-08-20 morning window) was introduced by a sibling session without a full gate
  rerun. Every session must rerun the full conformance gate before handoff, and bisect-attribute
  regressions before logging/fixing.

### Query-Source Alias Registration Invariants (QA-103, 2026-08-20)

When restructuring `_translate_query`'s placeholder-with-WHERE source branches in
`fhir4ds/cql/translator/expressions/_query.py`, EVERY branch that builds a
row-shaped FROM alias (`SELECT * FROM (...) AS <alias>`) must call
`add_alias(alias, table_alias=alias, cte_name=...)`. Dropping that registration
leaves only the earlier `ast_expr` registration, and `_translate_identifier`
then inlines the full 2-column `(SELECT patient_id, resource ...)` subquery at
every `<alias>.property` site — DuckDB "Subquery returns 2 columns" binder
errors plus silently uncorrelated (wrong-row) results. Related hardening kept
in place: `_narrow_to_resource_column` narrows explicit `[patient_id, resource]`
projections; `resolve_placeholders` in `placeholder.py` must traverse
`SQLSelect.order_by` (`Last(...)` lowering puts placeholders there → unresolved
`urn:cql:code` retrieve placeholders).

### CQL-05 EXPLORER launch addenda (QA-104..QA-107, 2026-08-20)

- Known fragile: strict casts lower to `CASE ... ELSE error('CQL strict cast
  failed...') END`; any code path that wraps arbitrary SQL in `TRY(...)` must
  keep `_contains_function_call` (`_operators.py`) recursing into `SQLCase`
  (when_clauses/else_clause/operand) or DuckDB rejects "TRY + volatile
  function" (QA-104).
- Known fragile: element access over retrieve-bound define aliases
  (`define L: [Observation]` + `First(L)` / `L[0]` / `L.first()`). The generic
  identifier path scalarizes these (LIMIT-1 row / multi-row scalar-subquery
  error); localized list sources live in `_definition_resource_cte_name`,
  `_translate_first_last_over_cte`, `_definition_resource_rows_list`
  (`_functions.py`) and are consumed by First/Last dispatch, the indexer, and
  method-form first/last/singletonfrom (`_lists.py`). Forward-referenced
  RESOURCE_ROWS defines are NOT detected (definition_meta fills in order).
- Known fragile: aggregating LIST-usage definition lookups generically (adding
  `list(sub.resource)` in `_core.py` identifier/promoted-lookup branches)
  breaks DQM — scalar-subquery flattening unwraps the aggregate next to bare
  `patient_id` columns ("patient_id must appear in GROUP BY", 47→28 observed).
  List coercion must happen at the consumer site, not in identifier resolution.
- Known fragile: `fhirpath_text` returns only the FIRST element of a
  multi-valued path. Any list-consuming translation over a
  `fhirpath_text(src, path)` node must swap to the list-returning `fhirpath`
  UDF via `_coerce_fhirpath_text_to_list` (Count→`array_length(fhirpath(...))`,
  First/Last→`LIST_EXTRACT(fhirpath(...), n)`) (QA-106).
- OPEN GAP (QA-107, deferred): list-literal query sources
  (`({1,2,3}) X return all X`) translate to row subqueries and are
  misclassified `RowShape.PATIENT_SCALAR`; `Count(L)` over such defines
  undercounts and `Sum` over filtered variants hits GROUP BY binder errors.
  Needs row-shape classification for list-typed query defines in
  `_translate_query`/definition-meta inference (converge with the Drift Log
  consolidation above), not per-shape patches.
- NOT A BUG additions: `Children({1,2,3})` → 0 (Children of a list is the
  per-element union, matching FHIRPath children(); scalars have no children);
  `convert '5 mg' to Quantity` → null (ToQuantity requires quoted-unit
  quantity-literal format, `'5 ''mg'''`); `convert Code/Concept to String` →
  null (no ToString overload for Code/Concept in the CQL 1.5 conversion
  table); `is FHIR.ObservationStatus` → TranslationError (enum/code-binding
  names are not FHIR ModelInfo types; clear failure is intended);
  First/Last over unordered retrieves may return either element (no ORDER BY).

## Milestone-5 Code Review (2026-08-20, CQL-01..CQL-05 delta)

Fifth milestone `code_review` launch reviewed the uncommitted diff vs
db1e4164 for the CQL-01..CQL-05 chunks. No new findings. Verification
highlights (see .ai_loop/code_review_findings.md):

- QA-103 DQM repair is structurally sound: add_alias restored at the
  row-shaped inner_query.where branch (_query.py:4525) alongside the intact
  QA-101 value-projection branch; placeholder ORDER BY traversal is a general
  AST fix. dqm_report.json 48/48 at 100%; structural+clinical parity 46/46.
- Clobber spot-check PASSED: all FP-11..FP-20 fix symbols
  (leastPrecisionDecimalPlaces, powerDecimalExactText,
  expandScientificToFixed, frac_digits, decimalFactorRatio,
  !explicit_namespace guard, fhirFieldType extension entries, operators.py
  membership raise) and CQL-01..05 symbols (cqlDivide, FHIR_TYPE_TO_CQL_TYPE,
  _validate_datetime_literal, same_code_unit_valid_for_compare,
  CompareTemporal, ORDER BY placeholder traversal) present.
- CQL extension binary fresh and md5-matched (10eaecdb...) across bundle +
  site-packages.
- REV-006/007 RESOLVED (verified). REV-001..005 remain OPEN hardening/debt
  (all LOW except REV-002 MEDIUM). Known residual: 7 FHIRPath integration
  parity failures outside the conformance gate (2 std::regex limits + 5
  temporal-edge fallback expectations).

## CQL-06 HISTORIAN (2026-08-20, spec compliance chunk: Type Operators — Conversion Checks)

- FIXED (QA-001 HIGH): `QuantityToString` now renders calendar-duration
  units as a bare keyword per CQL 1.5 Appendix B §ToString/Table 9-G
  ("ToString(4 days) results in `4 days`, i.e. not `4 'd'`"): units in the
  `_CQL_CALENDAR_DURATION_UNITS` registry emit bare (`4 day`), UCUM units
  stay quoted (`5 'cm'`). Single shared macro layer covers both backends;
  round-trip ToQuantity(ToString(q)) preserved. Regression test:
  `test_cql_to_string_renders_calendar_duration_keywords_bare_cql06_historian`
  (test_conversion_check_parity.py). Baseline 2832/2832 held.
- NOT A BUG registry: integer literals beyond Integer range without the
  `L` suffix correctly fail translation (`ConvertsToLong(2147483648)` →
  TranslationError) — CQL 1.5 requires the Long `L` suffix for Long
  literals; `ConvertsToLong(2147483648L)` translates and lowers correctly.
- NOT A BUG registry: C++ `to_quantity` (extensions/cql/src/cql/quantity.cpp)
  still accepts only the quoted-unit grammar, but the Python `ToQuantity`
  UDF (registered after extension load) is the serving path on both
  backends — no divergence is observable at the SQL surface (verified by
  dual-backend probes). If ToQuantity is ever moved fully native, the bare
  calendar-keyword alternative must be mirrored in quantity.cpp.

## CQL-06 EXPLORER Findings (2026-08-20, 3rd personality launch — RESOLVED in-loop)

- FIXED (QA-001 HIGH): `.value` (FHIR-to-System primitive value accessor)
  now works on every FHIR primitive path (`P.birthDate.value`,
  `O.status.value`, `(O.value as FHIR.string).value`).
  `_strip_primitive_value_segments()` in `fhir4ds/cql/translator/expressions/_property.py`
  drops a `value` segment when the accumulated prefix resolves to a FHIR
  primitive type via `fhir4ds/fhirpath/models/r4/path2Type.json` (data-driven;
  metadata misses like the choice-type prefix `Observation.value` keep the
  segment — conservative); the `as`-unwrap site maps
  `(X as FHIR.<primitive>).value` to identity by comparing the BARE last
  path component of the model-qualified cast target (NamedTypeSpecifier
  targets arrive as "FHIR.string"). FHIRHelpers-load-bearing: DQM 47/47 and
  FHIRPath 935/935 verified unaffected.
- FIXED (QA-002 MEDIUM): `ConvertsToDecimal` accepts any fractional digit
  count (`_DECIMAL_STRING_RE` format `(+|-)?#0(.0#)?`); representability is
  gated by `_fits_duckdb_decimal_rounded()` (integer-digit extent only;
  excess scale rounds like ToDecimal — CQL-01 doctrine).
- INTENDED per official fixtures (QA-003 reclassified): `ConvertsToTime`/
  `ToTime` ACCEPT timezone suffixes (`12:00:00Z`, `+05:00`) and normalize
  them away, because official cql-tests fixtures CqlTypeOperatorsTest
  ToTime2/3/4 mandate it (`ToTime('T14:30:00.0+05:30')` → `@T14:30:00.000`).
  Fixtures outrank spec prose (GLOBAL_RULES); invalid offsets like `+99:00`
  are still rejected via `_valid_timezone`. Run the conformance gate before
  landing any spec-strictness fix — the initial spec-prose-reading rejection
  broke the gate 1706→1703.
- NOT A BUG registry additions (verified vs CQL 1.5 §09-b this launch):
  `ConvertsToBoolean` case-insensitive t/f/yes/no/y/n/1/0; ToQuantity(Ratio) =
  numerator ÷ denominator yielding unit '1'; ConvertQuantity year→day 365.25 /
  month→day 30.4375 (UCUM Julian factors); ConvertsToX(null) = null;
  `ConvertsToInteger(O.value as String)` retrieve filters work correctly.
- Open observations (out of chunk, future QA): Tuple `{...}` return columns
  project as resource references (NULLs); ConvertsToQuantity/ToQuantity still
  hard-reject >8 fractional digits (QA-002 class).
- Harness note: unknown CQL function names (e.g. FHIRPath-ism `iif(...)`)
  pass through to SQL verbatim and fail at execution with Catalog errors —
  CQL's conditional is `if ... then ... else`.
- Milestone code review #6 (CQL-06..CQL-10, 2026-08-21): delta clean; no new
  findings. REV-001..005 remain the only open items (LOW/MEDIUM hardening).
  Binary freshness verified: cql.duckdb_extension md5 2722c674 (repo ==
  site-packages, mtime 07:01 > quantity.cpp 06:58); fhirpath.duckdb_extension
  md5 57d0634b (repo == site-packages, build 09:51 > evaluator.cpp 09:37); no
  ~/.duckdb cache copies. DQM gate 47/47 measures at 100.0%
  (conformance/reports/dqm_report.json); CQL-05 QA-103 repair intact
  (add_alias + order_by placeholder traversal symbols present). Live spot
  check: test_comparison_operator_parity.py 15/15.

## CQL-11 HISTORIAN Findings (2026-08-21, 2nd personality launch — RESOLVED in-loop)

- FIXED (QA-001 HIGH): Round/RoundTo macros
  (fhir4ds/cql/duckdb/macros/math.py) must use `system.floor` /
  `system.ceil` — bare `FLOOR`/`CEIL` names resolve to the CQL Floor
  macro (TRY_CAST AS INTEGER) registered in the same connection, which
  silently NULLs rounded values whose shifted magnitude exceeds the
  Integer range (RoundTo(123.456, 8) -> NULL; Round(3147483647.05) ->
  NULL). Also CAST -> TRY_CAST AS DECIMAL(38,8) so only
  Decimal-unrepresentable results null (spec: Round returns Decimal).
  Doctrine: any macro composed from other CQL-named macros must use the
  `system.` prefix for builtins, not just when names collide with its own.
- FIXED (QA-002 HIGH): Decimal arithmetic overflow now nulls instead of
  raising OutOfRangeException. `_decimal_static_arithmetic_unrepresentable`
  (exact Decimal fold of +,-,* literal trees; >= 1e30 integer extent ->
  NULL) + runtime TRY guard widened to `_numeric_static_operand_types`
  (Integer/Long/Decimal) in translator/expressions/_operators.py.
  DECIMAL(38,8) bounds: 30 integer digits; excess fractional scale still
  rounds (CQL-01 doctrine), it is not overflow.
- NOT A BUG registry: two-arg Max(a,b)/Min(a,b) is a non-spec convenience
  (Appendix B defines list-only aggregates; nulls ignored, so Max(1,null)=1);
  Min/Max of Quantities return the minimum/maximum ELEMENT in its own unit
  (comparison is unit-aware); 2 'cm' * 3 'cm' -> 6 'cm2' is spec UCUM unit
  multiplication; Precision(0.000000001) = 8 (literal rounds to the
  implementation scale before Precision sees it).
- Validation: probe .temp/qa/cql11_historian2_probe.py; new tests in
  test_arithmetic_part2_parity.py; conformance 2832/2832 held.

## CQL-12 EXPLORER launch (2026-08-21) — string operators doctrine
- CQL-12 EXPLORER doctrine: bracket indexing over CHAINED property navigation
  is LIST indexing (CQL 1.5 implicit property traversal), never character
  indexing — `Patient.name.given[0]` → 'Joel', `.code.coding[0].code` →
  '8480-6'. `_is_string_index_source` (fhir4ds/cql/translator/expressions/
  _lists.py) must not admit `fhirpath_text`/`fhirpath_scalar` chains as String
  sources; they lower to the list-returning `fhirpath` UDF + LIST_EXTRACT.
  Literal Strings, String-typed function results, and First()-demoted scalar
  defines keep the string Indexer ('t' of 'Montavon').
- CQL-12 EXPLORER doctrine: SplitOnMatches never includes capture groups in
  its result on ANY engine (Java Pattern.split semantics; no group-inclusion
  clause in Appendix B). The Python fallback filters `parts[::groups+1]` —
  do not reintroduce raw `re.split` results.
- CQL-12 EXPLORER verified-clean seams (dual-engine): empty-needle
  PositionOf=0 / LastPositionOf=length, overlapping substring positions,
  Substring zero-length/''-corners (start>=length→null doctrine), single-char
  Indexer, nested-quantified regex + optional-group substitution + empty-match
  replace, Combine null-element skipping, Concatenate non-String operands →
  typed TranslationError (Table 9-E: no implicit conversion to String).
  ReplaceMatches '$1' with no capture group → typed CQLRegexPatternRejected
  (Java-consistent) — intended.
- Pre-existing LOW drift (both list-index lowerings): negative DuckDB
  list_extract indexes wrap to the list end instead of CQL index<0 → null.

## CQL-13 Date/Time Operators Part 1 Launch (2026-08-21, SKEPTIC iter 1)

Spec-compliance launch CQL-13 (CQL 1.5 §8.1–8.8: Add/Subtract temporal
Quantity, After/Before with precision, Date()/DateTime() constructors,
Component From, Difference in precision between, Duration in precision
between), verified against live Appendix B (2019May STU4). Two dual-engine
fixes:

- **Week difference (§8.7)**: `difference in weeks` counts SUNDAY-first-day
  boundaries crossed, never truncated day-span/7. Python `_compute_difference`
  and legacy `differenceInWeeks` use the Sunday-based week index
  `ordinal // 7` (proleptic Gregorian ordinal 7 = 0001-01-07 is Sunday, so
  Sunday ordinals are ≡ 0 mod 7); C++ `ComputeDifferenceBetweenValue` uses
  `(jdn + 1) / 7` (JDN 0 is Monday, Sunday JDNs ≡ 6 mod 7). Duration in weeks
  stays whole-week truncation — Difference-vs-Duration distinctness is
  load-bearing and now pinned both directions.
- **Date + sub-day quantity (§8.1/§8.15)**: Date values (no 'T' marker) with
  hour/minute/second/millisecond quantity units (incl. UCUM h/min/s/ms) are
  NULL in `dateAddQuantity`/`dateSubtractQuantity` (Python) and
  `DateAddQuantityFunc`/`DateSubtractQuantityFunc` (C++), instead of the old
  silent convert-to-input-precision no-op (`@2024-01-01 + 1 hour` returned
  the date unchanged). Finer units on DateTime operands remain legal per the
  spec's convert-and-truncate rule (DateTime(2014) + 24 months → 2016;
  @T10 + 61 minutes → T11; decimal fractions ignored).
  Extension rebuilt/deployed md5 be8c0ba575df910c4e01f8459a47b32a.

NOT A BUG registry (verified conformant this launch): uncertain
difference/duration results surface as closed interval JSON
(`{"start":..,"end":..}`, e.g. months between @2012-01-02 and @2012-01 →
[0,10]) per §8.7/§8.8 spec examples; negative results when the first
argument is the later instant (timezone-aware, e.g. -07:00 vs -05:00 → -2
hours); After/Before stop-at-specified-precision → false (not null) when both
operands are equal through the requested precision; constructor/difference
results are VARCHAR integers; Z-suffixed offsets are preserved on Add.
Regression coverage:
`test_datetime_part1_parity.py::test_cql_datetime_part1_week_difference_and_date_unit_restriction`
(dual-engine) and updated `test_datetime_udfs.py` week-difference pins.
Gate fresh 2832/2832; pytest fhir4ds/cql 5754 passed / 9 skipped.

## CQL-13 HISTORIAN Findings (2026-08-21, 2nd personality launch — RESOLVED in-loop)

Second spec-compliance launch on CQL 1.5 §8.1–8.8, verified against live
Appendix B (2019May). Both SKEPTIC fixes re-verified regression-free.
Two new dual-engine fixes:

- **Sub-day Difference boundaries (§8.7 HIGH)**: `difference in`
  hours/minutes/seconds/milliseconds used elapsed-duration truncation
  (§8.8 Duration math) instead of counting boundaries crossed.
  `difference in hours between @2024-01-01T10:30:00 and
  @2024-01-01T12:15:00` returned 1, spec requires 2 (hour marks 11:00
  and 12:00 crossed; endpoint marks count, matching day-precision and
  the spec example @2012-01-01→@2012-02-01 = 1). Fixed as
  floor(epoch-millis/unit-ms) index difference (UTC-normalized for
  timezone-aware operand pairs, mixed aware/naive stays null) in Python
  `_subday_boundary_difference` (used by `_compute_difference` and
  legacy `differenceIn{Hours,Minutes,Seconds}`) and C++
  `ComputeDifferenceBetweenValue` + legacy DifferenceIn*Funcs with new
  `FloorDivInt64` (epoch millis are negative before 1970; C++ division
  truncates toward zero).
- **Time + day-level unit no-op (§8.1/§8.15 MEDIUM)**: `@T12:30 + 1 week`
  (also `1 day`, `1 'd'`) returned the input unchanged — the Time branch
  dispatched on `_TIMEDELTA_UNITS`, which includes week/day, so the
  2000-01-01 reference-date shift was invisible at time precision.
  Year/month already nulled; now all day-level units null on Time
  operands in both engines (Python Time-branch allowlist; C++
  `IsDayLevelUnit` guard in Date{Add,Subtract}QuantityFunc).

Extension rebuilt/deployed md5 c08b7f98656eff298ade8b4a7379043b.
DEFERRED (LOW): week-precision After/Before/same-as and cross-type
precision keywords (hour precision on Date operands; day/week units on
Time operands in duration/difference) evaluate leniently to null/0
instead of translation errors — spec allowlists exist
("comparisons involving weeks are not supported"), `week from` IS
rejected, but no wrong non-null value is produced; static per-type
precision rejection is net-new translator typing functionality.
NOT A BUG registry (verified this launch): Time + sub-day units wraps
modulo midnight (@T00:30 - 90 minutes → T23:00); convert-and-truncate
at sub-unit quantities (@T10 + 90 minutes → T11; 1500 ms on
second-precision Time → +1 s); timezone-normalized sub-day Difference
(@12:00-07:00 vs @12:00-05:00 → -2); sub-day duration/difference on
Date-only literals surfaces the uncertainty-interval convention
([0,47] hours). Regression:
`test_datetime_part1_parity.py::test_cql_datetime_part1_subday_difference_boundaries_and_time_unit_restriction`
(dual-engine) and corrected `test_datetime_udfs.py` pins
(differenceIn{Hours,Minutes,Seconds}: -4/-1/-1, boundary semantics).
Gate fresh 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47).

## CQL-14 Date/Time Operators Part 2 Launch (2026-08-21, SKEPTIC iter 1 — CLEAN)

Spec-compliance launch CQL-14 (CQL 1.5 §8.9–8.18: Now/Today/TimeOfDay, Same As
/ Same Or After / Same Or Before / On Or After / On Or Before [precision],
Subtract(DateTime−Quantity), Time() ctor), verified against live 2019May spec
HTML + official Cql.g4 + cql-tests XML, dual-engine. Three fixes:

- **Bare `same as` parse gap (MEDIUM)**: `A same as B` without precision was a
  ParseError for points AND intervals while `same or after/before` parsed —
  grammar `concurrentWithIntervalOperatorPhrase: 'same' dateTimePrecision?
  (relativeQualifier | 'as')` allows it and §8.12/§9.24 define no-precision
  semantics (compare at finest precision of either input, null when uncertain;
  intervals compare start+end). Parser now emits `same as`; translator routes
  points to cqlDateTimeEqual, intervals to start/end cqlDateTimeEqual AND.
- **Mixed Time/DateTime operand pairs (LOW)**: `@T13:36:12 same second as
  @2024-01-01T13:36:12.500` returned definitive false (zeroed date components
  of the Time operand). Same-type signatures mean the pair is undefined → now
  uncertain/NULL in Python `_compare_at_min_precision` /
  `_compare_at_specified_precision` and C++ `CompareTemporal` (`is_time`
  mismatch guard). Native rebuilt/deployed md5 506edd22a83b38fc0237a75263b41050.
- **Now() microsecond precision (LOW)**: Now() leaked DuckDB's 6-digit
  fractional seconds; the CQL DateTime model stops at millisecond. Truncated
  to 3 digits in the translator `now` registration and the `Now()` macro.

NOT A BUG registry (verified conformant this launch): timezone normalization
at hour-or-finer ONLY in same-family comparisons matches the Java reference
engine (`DateTime.getNormalized`: precision > DAY → evaluation-zone normalize),
so `same day` across ±offsets compares raw date components by design;
uncertainty semantics match every spec/official-test example (null when either
operand coarser than requested precision; definitive result when ordering
provable at a coarser component); Subtract mirrors CQL-13 Add (calendar
truncation Mar 31 − 1 mo → Feb 28/29, tz preservation, unit allowlists,
convert-and-truncate); Time() ctor trailing-null/null-below-specified/
out-of-range → null; `(-1) day` paren-neg quantity parse rejection matches
`quantity: NUMBER unit?` in Cql.g4 (`- -1 day` works); `'2012T'` is the
internal DateTime-with-no-time marker convention; Now()=Now() deterministic
within a library, Today() Date-only, TimeOfDay() second-precision Time.
Known duplication (architectural note, LOW): Now() SQL text exists in the
translator registry, the legacy `FunctionTranslator._translate_datetime_func`
(also bare CURRENT_TIMESTAMP, no offset — appears unexercised), and the
`Now()` macro; consolidate if that legacy path ever revives.
Regression: `test_datetime_part1_parity.py::
test_cql_datetime_part2_same_as_without_precision_and_cross_type` (dual-engine).
Gate fresh 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47).

## CQL-14 HISTORIAN Findings (2026-08-21, 2nd personality launch — RESOLVED in-loop)

Second spec-compliance launch on CQL 1.5 §8.9–8.18 (+ interval §9.24–9.26),
verified against live 2019May spec HTML (interval Same Or After/Before
sections quoted verbatim). All three SKEPTIC fixes re-verified regression-free.
Two fixes:

- **No-precision interval same-or-after/before (HIGH)**: `A same or after B`
  without precision, with interval or point-vs-interval operands, passed raw
  interval strings to the point-comparison UDFs; the native
  `ExtractTemporalOperand` substituted interval LOW for both operands
  (start-vs-start), producing definitive WRONG booleans —
  `Interval[@2012-01-01, @2012-01-02] same or after Interval[@2012-01-01,
  @2012-01-03]` returned true; spec §9.25 requires start(left) on-or-after
  END(right) → false. Python fallback returned null. Fixed in
  `_translate_same_operator` (_temporal_comparisons.py) by extracting
  intervalStart/intervalEnd exactly like the precision branches (§9.26
  same-or-before: end(left) vs start(right)); points unchanged. One translator
  fix, both engines, no C++ change. Architectural note (LOW): the native
  low-vs-low `ExtractTemporalOperand` behavior is now unreachable from CQL but
  remains a trap for direct-SQL UDF callers — remove or assert in a future
  native-touching launch.
- **Time(null) translation crash (LOW)**: single null literal argument to the
  Time constructor raised ValueError('Time constructor components must be
  Integer values') while Time(null,null)/Date(null)/DateTime(null) evaluate to
  null. §8.16 requires at least one specified component; a lone null now
  routes to the static-null constructor path → null. Non-Integer literals
  (Time(1.5)) still raise.

NOT A BUG registry (verified this launch): interval `same <prec> as` compares
start AND end (§9.24) with point operands treated as singleton intervals;
precision `same day or after` interval bound extraction was already correct;
no-precision point-only same-or comparisons and uncertainty nulls unchanged;
Time ctor trailing-null strip / null-gap / out-of-range nulls; Subtract
calendar truncation (Mar 31 − 1 mo → Feb 29/28), UCUM 'h'/'ms' units, tz
preservation, Time modulo-midnight wrap, fractional-quantity truncation;
`on or after/before day of` point/interval matrix; week precision → null.
Regression:
`test_datetime_part1_parity.py::test_cql_datetime_part2_no_precision_interval_same_or_and_time_null_ctor`
(dual-engine, 13 cases). Gate fresh 2832/2832 (ViewDef 144, FHIRPath 935,
CQL 1706, DQM 47); fhir4ds/cql/tests 4916 passed / 4 skipped.

## CQL-15 Interval Operators Part 1 Launch (2026-08-21, SKEPTIC iter 1 — CLEAN)

Spec-compliance launch CQL-15 (CQL 1.5 interval operators: After/Before [precision],
Collapse [per], Contains/In [precision], End of, Ends [precision], Equal/Equivalent,
Except, Expand [per], Includes). 4 issues found / 4 fixed / verified dual-engine.

- CQL-15 SKEPTIC doctrine (2026-08-21): `ends <prec> of X` is
  `start(left) >= start(right) AND end(left) == end(right)` at the precision —
  point operands promote to degenerate intervals [p,p] (EndsEvaluator.kt), so
  `Interval[1,5] ends 5` is FALSE. The old precision branch compared end equality
  only (QA-001 HIGH; `_translate_ends_op`).
- CQL-15 SKEPTIC doctrine (2026-08-21): `collapse(X, per)` must NEVER lower
  through expand — per extends each interval's end by `per` for the
  overlap/meets merge decision only; output intervals keep their ORIGINAL
  boundaries (reference CollapseEvaluator.getIntervalWithPerApplied). Temporal
  per of exactly 1 (or 0) does precision-based meets with no extension.
  Implemented as `collapse_intervals_per(list_json, per)` in BOTH
  `udf/interval.py` and native `CollapseIntervalsPerFunc`
  (cql_extension.cpp; rebuild+md5-deploy required); `collapse_intervals_per`
  is in `_PYTHON_PREFERRED_CPP_CONFLICTS` (Python = conformance authority).
  Documented boundary: dynamically incompatible per units no-op the extension
  (static ones are NULLed by the translator guard).
- CQL-15 SKEPTIC doctrine (2026-08-21): list `except` with a scalar Interval
  operand wraps ONLY literal Interval AST nodes in `list_value(...)` before
  `CQLListExceptEq` — never identifiers (list-typed defines must not be nested).
- NOT A BUG registry (CQL-15, verified against cql.hl7.org 09-b + reference
  engine): `null contains 3` → false and `3 in null` → false (spec says so,
  unlike most nullological operators); `end of Interval[1,null]` → point-type
  maximum (2147483647 / 9999-12-31); `end of Interval(1,5)` → predecessor (4);
  `Interval[1,5] except Interval[2,3]` → null (proper-interval rule); Except
  with equal intervals → null; collapse excludes null list elements;
  `expand ... per null` uses default per; Ends no-precision, Includes, Expand
  list/interval overloads, After/Before adjacency + open-bound semantics all
  conformant including spec examples.

**Hardened in CQL-15 HISTORIAN (2026-08-21).** Collapse `per` semantics
(reference `CollapseEvaluator.kt`): a temporal per of exactly 0 or 1 unit does
NOT extend bounds — the overlaps/meets merge decision runs at the PER-UNIT
precision (e.g. `{[2024-01-15,2024-01-31],[2024-02-02,2024-02-10]} per month`
merges via month-precision meets). per >= 2 extends the end bound numerically
for the decision only. Weeks have no comparison precision: per 1 week extends
by 7 days. Implemented in both `collapse_intervals` (Python,
`_temporal_precision_meets_or_overlaps` + "PRECISION_MEETS" sentinel) and native
`CollapseIntervalsPerFunc` (`TemporalPrecisionMeetsOrOverlaps`). Collapse output
serialization must preserve AUTHORED temporal precision of bounds (raw strings
"2024-01"/"2024-01-15T10") in both engines.

**CQL-15 HISTORIAN doctrine (2026-08-21): `collapse_intervals_per` is a
JSON-array-string list source.** Any new JSON-list UDF must be added to EVERY
translator recognition site that knows `collapse_intervals`:
`_JSON_LIST_FUNCS` (`_functions.py`), the list_transform known-list-source set
and from_json wrap (`_query.py`), and the First/Last JSON wrap (`_lists.py`).
Missing sites made `Sum((collapse X per) Y return ...)` emit a bare SQL
aggregate `SUM(...)` instead of `list_sum(list_transform(...))`, which is a
Binder Error when the enclosing boolean define lands in a WHERE clause — this
silently broke CMS128 (DQM 46/47) after the CQL-15 SKEPTIC launch even though
its handoff claimed a passing gate. Never trust inherited gate claims; rerun
the master gate after chunk-lowering changes.

**CQL-15 HISTORIAN doctrine (2026-08-21): `includes [precision]`
(interval-interval)** must route through `intervalIncludesPrecise` (mirroring
`included in`'s existing precise routing). Generic `precision of` translation
truncates only the wrapped operand's literal bounds and then compares at mixed
precision, collapsing determined results to NULL (e.g.
`Interval[@2024-01-05,@2024-03-31] includes month of Interval[@2024-01-01,
@2024-02-15]` must be TRUE, not null).

**CQL-15 HISTORIAN doctrine (2026-08-21): Expand null-boundary semantics.**
An OPEN null boundary ("will not contribute any results") returns an empty
list; a CLOSED null boundary is an implementation choice NOT to expand — both
engines return SQL NULL for closed-null (and for [null,null]). Python
`_expand_impl` and native `ExpandIntervalUnits` agree; do not regress to
excluding single closed-null intervals as `[]`.

NOT A BUG registry (CQL-15 HISTORIAN): `Interval[1,5] after Interval(null,0]`
is TRUE (After only consults end(B)); `expand { Interval[1,3],
Interval[5,null] }` excludes the null-bound element; Except results that would
be two disjoint pieces return null (single-interval rule); `end of
Interval(1.5,3.5)` is 3.49999999 (Decimal predecessor); Equal over
`Interval[100 'cm',5 'm'] = Interval[1 'm',5 'm']` is true (unit conversion);
`collapse X per -1` is a parse-time rejection (grammar's quantity literal is
unsigned; negative per is undefined) — deferred.

**CQL-15 EXPLORER (iter 1, 2026-08-22) doctrine: LIST_EXTRACT interval
operands.** Element selection over interval lists — `First({Interval[4,6]})`,
`Last(...)`, `(collapse ...)[i]` — lowers to `LIST_EXTRACT` which
`_is_fhir_interval_expression` (`_temporal_intervals.py`) must classify as an
Interval operand for ALL §9 operator routing sites (contains/in, includes,
after/before, =/~, starts/ends, except, start/end of, expand). Without it,
contains/in degrade to DuckDB string-contains Binder Errors and the
`{low,high}` bounds-list coercion silently re-wraps the selection as a
degenerate `intervalFromBounds(x,x)` (wrong-boolean, not an error). Any new
interval-UDT-producing function name must be added to this recognizer's
LIST_EXTRACT source check (currently: intervalFromBounds/Except/Intersect/
Union calls, SQLList/SQLArray elements, `from_json(collapse_intervals[_per])`).

**CQL-15 EXPLORER (iter 1, 2026-08-22) doctrine: Expand per-precision
boundary truncation is LOW-ONLY.** CQL 1.5 §9: boundaries more precise than
per are truncated to per precision — but only the LOW boundary moves to the
per grid; per-grid starts compare against the ORIGINAL (authored) high bound.
Official fixture: `expand Interval[@T10:00, @T12:30) per hour` →
{T10, T11, T12}. Applying the predecessor (`_sub_step`/SubtractExpandStep) or
truncating the high breaks ExpandPerHourOpen (CQL 1704/1706). Boundaries LESS
precise than per contribute nothing for Date/Time
(`Interval[@2024-01,@2024-01] per day` → {}). Numeric expand is grid-from-start
with NO low truncation, matching the HL7 DBCG Java reference engine
(`expand Interval[1.2,3.0] per 1` → [1.2, 2.2]) — reference/fixtures outrank
spec prose. Implemented in `_expand_temporal`/`_expand_time`
(udf/interval.py) and `ExpandTemporalInterval`/`ExpandTimeInterval`
(cql_extension.cpp); native rebuild + md5-deploy required after C++ edits.
NOT A BUG: `(collapse {Interval[1,2], Interval[4,6]} per 2)[1]` is null —
per 2 spec-merges to a single Interval[1,6], so index 1 does not exist.

## Code Review Milestone #7 (2026-08-22, review-35 delta CQL-11..15)
- REV-008 (HIGH): site-packages cql.duckdb_extension is stale (025c79ed vs repo 98a8c858) — re-deploy before any wheel build / pre_release pass.
- REV-009 (MEDIUM): DQM CMS871 FHIRHelpers load fails intermittently ("'Token' object is not subscriptable", 1 of 2 identical sequential runs; shared library_cache in run_dqm.py:139 is a suspect). DQM gates must retry loader ERRORs before declaring pass/fail.
- REV-001/REV-004 resolved by fhirpath native rework; REV-002/003/005 remain open debt.
- Gate-claim discipline: inner launches must re-run the DQM suite against the FINAL tree state and record both extension binaries' md5s across repo/site-packages in the handoff.

**CQL-17 SKEPTIC doctrine (2026-08-22):** interval-operator translator dispatch
must recognize interval-typed operands at the CQL AST level, not only by
SQL-shape recognition — `(null as Interval<T>)` lowers to a null CASE that
`_is_fhir_interval_expression` misses, and union silently fell into list
semantics (BinderException or `[]` instead of §19.31 null) while
intersect/except/properly-includes were conformant. `_translate_union_op`
now resolves `_static_structural_type_name(...)` `Interval<` types. Quantity
interval outputs must be valid JSON with the UCUM `system` field across
Python fallback and native: `intervalWidth` and `start/end of` Quantity
intervals were the remaining non-conformant siblings after the HISTORIAN
Size fix (`_raw_closed_bound` orjson-serializes dict bounds). Probe rule:
typed-null operands of every structured type through every dispatch, and
audit all sibling operators when one gets an output-shape fix.

## CQL-18 re-launch doctrine (2026-08-22): dynamic FHIR list operands
CQL list operators over RETRIEVED multi-valued FHIR fields (name.given,
telecom.system) must receive the full list projection, not the scalar
`fhirpath_text` lowering (first-node truncation). Centralized in
`_promote_fhirpath_text_list()` (fhir4ds/cql/translator/expressions/_utils.py)
and applied across the list-macro helpers, Equivalent dispatch, the Contains
fallthrough (equality semantics, never substring, over dynamic FHIR paths),
the Exists fhirpath_bool branch, the Distinct fallback, IndexOf dispatch, and
the `flatten` pre-translate. Testing doctrine: chunk operators must be probed
end-to-end through patient-context population SQL with real FHIR resources —
the static-literal surface alone passed three prior personalities while every
dynamic path was broken (exists silently false with data present).
Follow-up (architecture): the scalar-vs-multi-valued property distinction is
not statically modeled in the translator; a multiplicity-aware property
typing layer is the long-term fix.

## CQL-19 SKEPTIC launch doctrine (2026-08-22): list-ops part 2 dynamic gap
The CQL-18 `_promote_fhirpath_text_list()` promotion was applied to the
Part-1 operator family only. Part 2 sites that still truncate dynamic
multi-valued FHIR fields to the first node (translate-level, py==cpp==nopy):
Skip/Take (`_lists.py:_translate_skip/take_expression` — Take character-slices
VARCHAR, Skip/Tail hit array_length(VARCHAR) binder), Length list branch
(`_functions.py` — returns string length of first node), SingletonFrom,
`_translate_union_op` list branch (binder errors; also SELECT * FROM CTE
inside Distinct wrap -> multi-column subquery), and properly includes/
included in over dynamic lists (silent False with data present). Tail over a
stored-list define alias of a dynamic field returns [] (rows-to-list wrap
misses). Spec adjudications: list union with null operand returns the other
list (cqframework issue #887; 2019May prose stale); `null properly included in
{'s','u','n'}` is FALSE per fixtures (ProperInNullRightFalse) contradicting
the spec prose example — fixtures win; Skip/Take/Tail null LIST -> null.
INTENDED: Boolean-define population boundary presence-encodes null as false;
verify 3VL through `{ (expr) }` lifted contexts (all conformant here).

## CQL-19 SKEPTIC launch doctrine (2026-08-22): list-ops part 2 + union gating
FIXED this launch (translator-only; see CQL-19 entry in .ai_loop
GLOBAL_KNOWLEDGE): Length/Tail/Skip/Take/SingletonFrom/Union/ProperlyIncludes
now promote dynamic multi-valued operands (args[0] promotion in
_translate_function_ref; stored-list alias operands skip AST inlining and
rows-coercion; singleton-from recurses into the cardinality CASE with the
typed >1 error; union normalizes operands via _union_operand_as_list + a
list-list Distinct(list_concat) branch; properly includes/in promote before
the list gate with widened _properly_is_list recognition).
CRITICAL GATING INVARIANT: RetrievePlaceholder is rows-shaped but NOT a rows
SQL type — any isinstance-based rows gating in union/set-op dispatch MUST
include RetrievePlaceholder, else DQM retrieve unions collapse to the
jsonConcat fallback with unresolved CTE identifiers (CMS117/122/124/125/130
regression, caught by the recovery gate). Define-level stored-list marking
for unions must be restricted to Property/List operands — resource-define
unions must keep row semantics. NOT A BUG registry: list union with a null
operand returns the OTHER list (cqframework issue #887; cql.hl7.org 2019May
prose "either null -> null" is stale); `null properly included in {'s','u','n'}`
is FALSE per official fixtures (ProperInNullRightFalse) contradicting the
spec prose example — fixtures win; Skip/Take/Tail null LIST -> null, null
count: Skip -> whole list, Take -> empty.

## CQL-19 HISTORIAN launch doctrine (2026-08-22): list-ops part 2 consumers
FIXED this launch (translator-only; see CQL-19 HISTORIAN entry in .ai_loop
GLOBAL_KNOWLEDGE + ARCHIVE_LOG): Count(<retrieve> union <retrieve>) now
resolves resource-define aliases to Retrieve ASTs and wraps the rows-union in
a patient-correlated COUNT(*) subquery (was BinderException "Subquery returns
2 columns"); `singleton from <stored-list define alias>` now counts list
ELEMENTS via the §20.30 cardinality CASE (was silently the whole list — the
subquery branch counted CTE ROWS); `dynamicList union null` returns the other
list flat (was nested [[...]] — three stacked causes: §20.29 null gate missed
statically-null CASE operands, `_is_static_null_case` rejected CASE-without-
ELSE which evaluates NULL, and the define-level stored-list union marking
rejected null/`as`-cast operands so the population wrap LIST()-nested);
`([A] union [B]).field` raises the typed TranslationError like
`[Resource].field` (was opaque binder error). NOT A BUG: retrieve-union row
ORDER is nondeterministic across engine modes (content + dedup conformant;
list-union order unspecified). Regression tests in test_list_part2_parity.py
(historian-suffixed). Gate: 2832/2832 incl. DQM 47/47.

## CQL-19 EXPLORER launch doctrine (2026-08-22): retrieve-shaped list operands
QA findings (translator-level, py==cpp==no_python; reproducers in
.temp/qa/cql19x_explorer_probe.py + inline population-SQL isolation):
(1) union over an alias-of-alias define (`A: {1,2,3}; B: A; B union {9}`)
emits `(SELECT * FROM "B")` — the 2-column stored-list CTE — into scalar
context (BinderException 'Subquery returns 2 columns'); SKEPTIC's
_union_operand_as_list detects direct stored-list defines but not depth-2.
(2) Tail/Skip/Take/Length over retrieve-shaped operands are broken end to
end: bare `Tail([Observation])` lowers to `Tail("Observation")` (column
ref), query returns `[Observation] O return O.id` lower to a SCALAR
subquery consumed as a list (scalar-subquery-multiple-rows / ARRAY_SLICE /
array_length(JSON|VARCHAR) binder errors), while Last/First/flatten already
wrap the subquery into a list. (3) `singleton from ([Observation] O return
O.id)` with >1 element silently returns NULL instead of the typed
SingletonFrom error. NOT A BUG Registry: `{1,2} !~ null` is TRUE — CQL 1.5
Equivalent is null-tolerant (null~x false, so !~ true; Appendix B Not
Equivalent / 04-logicalspecification); Skip/Take negative counts return []
(DuckDB slice semantics, pinned by SKEPTIC direct-SQL probes).

## CQL-19 EXPLORER launch outcome (2026-08-22): retrieve-shaped list operands
FIXED this launch (translator-only, binaries unchanged; architect-audited
CLEAN iter 1): (1) stored-list DefinitionMeta (stores_list_value /
PATIENT_SCALAR / List< cql_type) now PROPAGATES through alias defines
(`define B: A`) in translator.py — depth-2 aliases are recognized by union
and list-operator stored-list detection. (2) New
`_lists.py::_list_operator_full_list_source` +
`_list_operator_source_is_retrieve_shaped`: materializes bare retrieves,
resource-define aliases, retrieve unions, query returns, and element-rows
defines into a correlated per-patient `COALESCE(list(...), [])` for the
Tail/Skip/Take/Length/SingletonFrom family (wired via _functions.py
dispatch and skip/take; First/Last keep window paths). DISCRIMINATORS that
must survive refactors: (a) `_union_operand_as_list` element-rows
conversion is PEER-shape-guarded (`peer_rows`) — without it DQM resource
unions degrade to ltrim(VARCHAR[]) binder errors (CMS117/CMS645); (b)
singleton-from >1 on the rows-subquery branch stays NULL by adjudication
(gate fixtures outrank §20.30 prose — raising regressed CMS1017/CMS832
eager-vs-short-circuit; element-exact paths keep the typed error). Pinned by
explorer tests in test_list_part2_parity.py (47/47); master gate fresh
2832/2832 incl. DQM 47/47.

## CQL-20 Aggregate Functions — HISTORIAN launch findings (2026-08-22)

- Literal/spec-example aggregate surface fully conformant (86/86 Appendix B
  examples + null/empty semantics, py==cpp). Residual defect class after the
  SKEPTIC pass was AGGREGATE RESULT TYPING on dynamic operands: the generic
  row-aggregate lowering casts elements to DOUBLE (Decimal precision lost:
  dynamic Sum{0.1,0.2} → 0.30000000000000004; Integer → DOUBLE).
- Cross-cutting hazard: widening `_static_list_element_types` inference can
  silently change lowering routes far from the edit — CMS128
  (CumulativeMedicationDuration `Sum(... all(...) + 1)`) regressed to
  46/47 DQM until unknown-typed operands were restricted to plain
  Identifiers. Always run the DQM suite after touching type inference.
- Pre-existing (deferred): Ratio tuple accessor `.numerator.value` returns a
  list in test_temporal_complex_parity.py — fails on the pre-launch tree.

## Spec-Compliance Milestone Review #8 — CQL-16..20 (2026-08-22, code_review launch)

- Clobber spot-check: all CQL-16..20 fix symbols intact (interval sentinels
  int64/Quantity, open-bound native intersect, cross-numeric bounds,
  `_promote_fhirpath_text_list`, stores_list_value/stores_patient_list markers
  with alias propagation, union peer-gating, full-list materialization,
  SingletonFrom, sub-day Difference, Duration uncertainty, shifted-deviation
  statistical macros, cte_manager UNKNOWN guards). No lost hunks.
- Binary freshness: cql extension md5 3e7d4167... matches repo bundle AND
  site-packages, mtime > sources — REV-008 RESOLVED. fhirpath 57d0634b...
  matched. No stale ~/.duckdb cache copies.
- DQM live run on final tree: 47/47 (100.0%), no loader error this pass
  (REV-009 still open — single run inconclusive).
- NEW REV-010 (MEDIUM): the dynamic-list shape-selection DETECTION layer
  (translator.py:1726-1900, _operators.py:4170-4230) accretes chunk-tagged
  syntactic carve-outs (five stacked detection paths + peer_rows gating +
  dead redundant Retrieve guards). The metadata model (RowShape /
  stores_list_value / has_resource) is principled; detection should be
  consolidated into one type-driven classifier — every new syntactic special
  case risks silently rerouting DQM resource unions (three regressions this
  period). NEW REV-011 (LOW): shifted-deviation macros re-anchor per
  expansion (perf note).

### CQL Message (CQL-22 launch, SKEPTIC) — verified conformant / INTENDED gap

- CQL 1.5 App B §Message verified end-to-end (translation + DuckDB execution, python-fallback
  AND C++-backed connections): source passes through unmodified with type fidelity (Integer
  typeof, lists, DateTime, Quantity, null, uncertainty intervals from imprecise birthDate);
  only severity `Error` stops evaluation (raises `code: message`); case-insensitive 'ERROR'
  raises; literal-false and null conditions fold to bare source ("performs no processing at
  all"); runtime parameter condition/severity decide at execution; Message works inside
  where-clauses (raises per offending row at Error, filters only at Warning); code accepts
  integer tokens per spec ("a token (like a string or integer)").
- INTENDED GAP (do not force-implement): the informational message channel (Trace/Message/
  Warning surfacing to the calling environment) is unimplemented — a translate-to-SQL engine
  has no logging channel; official fixtures (CqlErrorsAndMessagingOperatorsTest.xml, 4/4
  green) do not pin it.
- Regression suite: fhir4ds/cql/duckdb/tests/integration/test_message_parity.py.

### CQL Message (CQL-22 launch 2, HISTORIAN 2026-08-23) — composition contexts verified conformant

- Second personality pass (HISTORIAN) probed axes beyond the SKEPTIC battery, python-fallback
  AND C++-backed paths identical throughout: Message embedded in arithmetic (`1 +
  Message(2, true, 'E', 'Error', ...)` raises), in list constructors, in Coalesce, and in an
  untaken iif ELSE branch (does not raise); chained Message (outer code surfaces in the
  raise); runtime severity case variants ('error'/'ErRoR' raise case-insensitively;
  Trace/Message/Warning/'Fatal' pass through); null and statically-false condition
  expressions return source; Tuple and Interval sources; population-SQL query contexts
  (Error severity in where/return/let clauses raises per offending row); Sum over Message
  elements exact DECIMAL(38,8).
- NOT A BUG Registry: `where Message(true, cond, ...)` keeps ALL rows by design — the
  operator returns its SOURCE operand (spec: "the result of the operation is the input
  source"), not the condition. Do not write tests expecting a where-clause Message to
  filter on its condition.
- UNCONFIRMED-LOW observation: raised error text format `code: message` is engine-defined;
  null code yields a leading ': ' separator. Spec/fixtures do not pin error text.
- Zero code changes; conformance gate 2832/2832 (DQM 47/47 first pass).

## SOF-VD-01 launch note (2026-08-23)
- ViewDefinition.fhirVersion binding now enforces the official R6 FHIR-version code set (24 two-segment [publication].[major] codes) that the SQL-on-FHIR IG 3.0.0-ballot (FHIR 6.0.0-ballot5) binds to. Three-segment ('4.0.1') and milestone ('5.0.0-snapshot1') codes are rejected per the required binding; refresh fhir4ds/viewdef/metadata.py:FHIR_VERSION_CODES from https://build.fhir.org/codesystem-FHIR-version.json when FHIR publishes new versions. Suite-level fhirVersion metadata in official spec_tests JSON files is NOT the element binding.

## SOF-VD-01 HISTORIAN launch note (2026-08-23)
- ViewDefinition.resource required binding: build.fhir.org valueset-resource-types.json (120 codes, system http://hl7.org/fhir/fhir-types) now includes the new R6 resource `DeviceAlert`; KNOWN_FHIR_RESOURCE_TYPES lacked it (QA-001, fixed this launch). Refresh the resource-type set from that value set when FHIR adds resources — but keep the R4–R6 cross-version superset (39 legacy codes like ChargeItem/Contract/Transport are absent from the current R6 value set yet still valid for fhirVersion 4.0/5.0 views; intentional, NOT A BUG).
- ViewDefinition root `resourceType` metadata must equal the canonical 'https://sql-on-fhir.org/ig/StructureDefinition/ViewDefinition' or be absent — implementation convention; official spec_tests never set it. NOT A BUG.
- `profile` canonical values are validated as non-empty strings only (no URL format enforcement) at parse AND generate time — matches reference-tool leniency. NOT A BUG.

## SOF-VD-02 HISTORIAN launch note (2026-08-23)
- Decimal constants MUST serialize as plain fixed-point FHIRPath literals: Python `str(float)` switches to exponent notation for |v| < 1e-4 or |v| >= 1e16, and the FHIRPath N1 grammar has no exponent — both engines fold `1e-05`-style literals to empty silently. Fixed in `fhir4ds/viewdef/constants.py::_resolve_simple_value` (Decimal + `format(d,'f')`, forced fractional part). Same class of bug as the SKEPTIC integer64 fix; keep both guards when touching `resolve_constant`.
- `parse_view_definition` parses JSON with `parse_float=Decimal` so 18-digit FHIR decimal precision survives to the substituted literal. Tests asserting parsed decimal values must compare against `Decimal`, not float (Decimal('1.2') != 1.2).
- Environment: loading the native fhirpath extension in fresh connections requires `duckdb.connect(config={"allow_unsigned_extensions": True})` + LOAD of the repo bundle path; `register_fhirpath()` returning False means Python fallback UDFs are active.
- Known fragile area (historical): any textual substitution of Python numeric values into FHIRPath expressions is exposed to literal-grammar mismatches (int32 range, exponent notation). Check `resolve_constant` first when constants evaluate to silent empty.

## SOF-VD-03 HISTORIAN launch note (2026-08-23)
- /mnt/d/sql-on-fhir-v2/tests/*.json are STALE DRAFT-format fixtures ('title' not 'name', no ViewDefinition.resource, top-level `column`, legacy nested `"type"` keys, integer-valued Quantity in fn_boundary). Running them raw shows ~60 divergences that are ALL draft-format artifacts, not implementation bugs (e.g. 'top level column' is correctly rejected because `select` is 1..* per models.fsh). The authoritative conformance suite is the sql-on-fhir.js snapshot in fhir4ds/viewdef/tests/spec_tests/. Do NOT treat the IG clone's /tests directory as a conformance source; the IG clone's value is input/fsh/models.fsh + input/pagecontent/ (processing_model.md is the normative algorithm text).
- Select semantics verified against processing_model.md beyond the SKEPTIC pass: (1) an empty row-part (nested select with forEach on an absent path, or a unionAll whose every branch is empty) suppresses ALL rows of the parent — Cartesian product with an empty part has zero tuples; (2) unionAll rows are evaluated per-focus of the enclosing select's forEach and ordered last (column, forEach selects, unionAll); (3) a bare `{}` select is spec-legal (column 0..*) and contributes no columns; (4) unionAll-only selects emit just the union rows; (5) `id | id` is a singleton because FHIRPath `|` de-duplicates — use `id | name.family` for a genuine multi-value runtime-guard probe.
- NOT A BUG: SQLGenerator(strict_collection=True) statically rejects collection=false paths that LOOK multi-valued even when data is singleton (e.g. name.given). The default generator is spec-exact (value when singleton, runtime error only when multiple values are actually produced); strict mode is an opt-in extra-strict profile used by the conformance adapter.

## SOF-VD-03 EXPLORER launch note (2026-08-23)
- Clean launch, zero defects. EXPLORER probes (deep 5-6-level nesting, sibling×unionAll×forEach, complex column.path at nested contexts, NULL propagation, deep name collisions, collection at depth, exotic descriptions, generation determinism, native/fallback parity) all spec-conformant.
- NOT A BUG registry additions: (1) unionAll arms = enclosing select's columns + branch columns, branch rows CARRY the enclosing columns and there is NO standalone base row when unionAll exists (matches union.json "unionAll + column" fixture — an "enclosing-only" row never appears); (2) unionAll branches with mismatched column TYPES (e.g. code vs string) are rejected — models.fsh unionAll invariant says "same column names and types", stricter than the name/order-only official fixtures; (3) deep (grandparent vs grandchild/great-grandchild) column-name collisions and unionAll-branch-vs-enclosing-column collisions are rejected at PARSE time (ParseError) before generation; (4) columns inside a forEach select are focus-relative — a bare `id`/`gender` column inside forEach contact yields NULL by design (use %resource.id); this repeatedly trips hand-written probes, not the engine.

### Milestone review #9 (CQL-21..22 + SOF-VD-01..03, 2026-08-23, code_review launch)
- cqlUncertain{Add,Subtract,Multiply,Compare,Min,Max,ListMin,ListMax,ListSum}: dual Python/native implementations; native wins on DuckDB 1.5.x via extension.py _SafeConnection skip. REV-012 (MEDIUM): Python fallback parser (udf/datetime.py `_parse_int_or_interval`) is lenient vs native fail-closed ParseUncertainRange (missing-key defaults to 0, no low/high aliases, AttributeError on float strings); only the native path has test coverage. Keep the two parsers doctrinally identical or the fallback will silently diverge.
- viewdef metadata.FHIR_VERSION_CODES is the spec-published full codesystem binding (63 codes incl. parent-level) — do not trim to child-only codes; the required binding includes both hierarchy levels.
- Deployment invariant verified this milestone: cql binary md5 c5b22d58 fresh across repo/site-packages/build-tmp; fhirpath 57d0634b fresh.

## SOF-VD-04 launch note (2026-08-23)
- column.{collection,type,tag} chunk CLEAN (1 MEDIUM + 1 LOW fixed). Parser now enforces a column-field allowlist (`_COLUMN_FIELDS` in fhir4ds/viewdef/parser.py: name,path,description,collection,type,tag) — unknown column fields AND unknown keys inside tag objects are ParseErrors, matching the reference validator schema's additionalProperties:false. Do not add "lenient passthrough" fields without extending that set.
- element-ID `column.type` (e.g. 'Observation.referenceRange', also normalized from full '#'-fragment URIs) whose leading resource segment differs from ViewDefinition.resource is rejected at GENERATION time (`SQLGenerator._validate_element_id_column_types`). Same-resource element-ID declarations intentionally keep the cardinality-only runtime guard because `type().name` cannot identify backbone element shapes portably — NOT A BUG.
- Pinned behaviors (NOT A BUG / spec-legal): collection=true emits a DuckDB LIST (element casts for numerics/booleans; empty list for absent paths; JSON strings for non-primitive elements); non-primitive output with type unset errors at runtime on BOTH engines; correctly typed non-primitive columns emit the JSON representation; unknown relative type URIs and System names ('String') are rejected at generation with the supported-type list; tags are validated (name/value required non-empty, duplicates allowed) but never consumed by generator/runtime — ansi/type-style hints do not alter output; no official spec_tests fixture exercises column.tag.

## SOF-VD-05 HISTORIAN launch note (2026-08-23)
- Nested-select chunk CLEAN under 19 new-composition probes (.temp/qa/sof_vd05_historian/probe.py); both SKEPTIC fixes re-verified at depth (unknown select-field rejection, minItems:1 empty containers — including inside unionAll branches).
- New pins: unionAll branch may itself contain nested select+forEach (rows set-equal — unionAll row order is spec-unpinned; NEVER order-assert across union branches); %rowIndex resets inside nested unionAll branches; nested select under repeat is supported; duplicate names rejected across nested-select vs unionAll branch and at depth 4; 25-level identity nesting fine.
- Column `type` must match the FHIR primitive type of the path at runtime ("string" on birthDate errors — declare "date"; fixtures do). `repeat` is an ARRAY of FHIRPath strings (fixtures: "repeat": ["item"]).
- INTENDED (QA-001 LOW): fhirpath_repeat collects only complex (dict) elements; primitive-yielding repeat paths (e.g. ["contact.name.given"]) return empty on BOTH engines. The v2 SD defines no select.repeat; legacy fixtures only traverse objects; upstream sof-js (main) removed repeat. Do not "fix" without a fixture pin.

## SOF-VD-05 EXPLORER launch note (2026-08-23)
- Nested-select chunk CLEAN (0 fixes; 1 LOW INTENDED). Normative ground truth pinned from spec source (releases branch, ViewDefinition-notes "Formal Semantics" Process(S,N)): (1) select columns are evaluated against the ITERATED focus when forEach/forEachOrNull is on the same select — parent-scope columns like `id` correctly yield NULL under `forEach: contact`; (2) sibling selects, nested selects, and unionAll are "parts" combined by CARTESIAN PRODUCT ("Sibling selects are effectively cross joined"), so a nested select emitting zero rows suppresses ALL rows for that focus — by design, not a bug; (3) in the forEachOrNull empty-collection null row, columns with path %rowIndex bind to 0, all others to null.
- unionAll branch-schema mismatch where a branch's columns come from a NESTED select (not direct columns) is accepted by the permissive parser but rejected by SQLGenerator.generate() with a precise recursive-schema ValidationError before execution — intentional parse-permissive/generate-strict split; do not "fix" by moving the check into the parser.
- NOT A BUG (QA-001 LOW): ViewDefinition constants are referenced only via `%name` placeholders (spec: "%[name]" substitution before evaluation). The FHIRPath backtick form `%`+"`name`"+` references an ENVIRONMENT variable, which is undefined — the "undefined environment variable" error is correct at every nesting depth.
- Verified at depth: name-collision rejection (depth 10), 10-level identical-path nesting with unique deterministic aliases, %rowIndex independent counters across sibling selects, constants in where at depth 5.

## SOF-VD-06 HISTORIAN launch note (2026-08-23)
- forEach chunk re-confirmed CLEAN (0 fixes; 2 LOW INTENDED). New pins vs SKEPTIC: column+forEach on the SAME select is the canonical spec form (SD forEach definition references "the corresponding column structure"); forEach works inside unionAll branches AND unionAll nests under a forEach select (per-focus cross join); column.constant is NOT a v2 Column field (rejected; constants are the top-level `constant` array, singular misspelling gets a helpful error); %parent is not a builtin (FHIRPATH_BUILTIN_VARIABLES = rowIndex/context/resource/rootResource/ucum) and is correctly rejected; forEach over mixed-type primitive collections and over explicitly-empty JSON array elements behaves per FHIRPath flatten semantics.
- INTENDED: forEach+unionAll on the same select is accepted (no SD constraint forbids; sql-expressions only forbids forEach+forEachOrNull) — semantics spec-silent, output deterministic; nested lateral joins carry NO row-order guarantee (spec imposes none; never order-assert across unnest levels).
- QA harness pitfalls that masqueraded as bugs (all bisected to probe bugs): harness norm() json.loads numeric strings ("11111" -> int); stray resource-shaped keys (e.g. `contained`) inside the VIEW dict are silently ignored by the parser — fixtures must live in the resource; nested-select column paths are focus-relative. Probes: /mnt/d/fhir4ds/.temp/qa/sof_vd06_historian/p1-p10.
- Gates fresh: viewdef pytest 1185, ViewDef conformance 144/144, run_all.py 2832/2832; fhirpath.duckdb_extension md5 57d0634b6ee6eddee9fc06a1355bef5a repo==site-packages (no rebuild).

## SOF-VD-06 EXPLORER launch note (2026-08-23)
- forEach/forEachOrNull chunk third personality, chaos pass: CLEAN (0 fixes; 2 LOW INTENDED). Chunk triangulated across SKEPTIC/HISTORIAN/EXPLORER — closed.
- New pins (native==fallback parity on all): heavy FHIRPath forEach targets are fine — exists()-gated iteration, `where().first()` targets, iif()-driven branch targets, filtered `extension.where(url=...)`, `contained.ofType(Observation)` fast path under iteration, BackboneElement chains at depth (`identifier.type.coding`). FHIRPath JSON-null array elements `[a,null,b]` are excluded from the collection, so iteration yields no row for null and `%rowIndex` counts the FILTERED collection (both iterators). A forEach/forEachOrNull expression that ERRORS at FHIRPath evaluation (e.g. type error inside a where) degrades uniformly to tolerant-empty: forEach -> 0 rows, forEachOrNull -> 1 null-preserved row (Process(S,N) defines no error semantics; identical on both engines — do not "fix" one iterator to raise). List-valued %constants are inexpressible per SD (constant value[x] are primitive singletons) — parser rejection of `valueCode: [..]` is correct; mandate items about iterating %constant lists are out of spec. `%rowIndex` composes with arithmetic and where clauses at depth 3-5; depth-5 nesting generates exactly one flat JOIN LATERAL per level, deterministic SQL. `$this = %context` is true per iterated focus at depth 2; `%rootResource` resolves from depth. Singleton boolean/count() foci yield one row.
- Probe-harness note: multi-item input to a singleton string function (`name.given.substring(0,3)`) errors engine-side (FHIRPath singleton doctrine) — surfaces as empty under forEach, NOT a viewdef bug; use `.select(substring(..))` or `.first().substring(..)` for mapped semantics.
- Probes: /mnt/d/fhir4ds/.temp/qa/sof_vd06_explorer/p1-p4 (p3 = forced-Python-fallback parity via duckdb.__version__ monkeypatch). Gates fresh: viewdef pytest 1185, ViewDef 144/144, run_all.py 2832/2832 FIRST PASS; fhirpath.duckdb_extension md5 57d0634b6ee6eddee9fc06a1355bef5a repo==site-packages (no rebuild).

## SOF-VD-07 SKEPTIC launch note (2026-08-23)
- select.repeat chunk: all 19 official repeat.json fixtures set-equal via official-runner adaptation; %rowIndex under repeat is a 0-based per-repeated-row counter (correct); repeat+where on same select filters repeated nodes; parser rejects repeat-as-string / empty array / repeat+forEach / repeat+forEachOrNull (SD constraint). Canonical SD ground truth (main branch XML): repeat 0..* string, "recursively follow each path to any depth ... combined using a union operation"; the RELEASED ig/2.0.0 SD snapshot has NO repeat element (repeat is main-branch + fixtures only).
- NEW pins (NOT A BUG): (1) union dedup is VALUE-based (serialized-node `=` equality per FHIRPath union semantics) — distinct-but-identical sibling subtrees collapse to one row; no fixture pins node-identity dedup, do not "fix" without one. (2) repeat row order is unnest order, not document order — spec imposes no row order, official runner sorts; never order-assert. (3) primitive-yielding repeat paths return empty (SOF-VD-05 pin re-confirmed). Overlapping repeat paths (["item","item"], ["item","item.item"]) correctly dedup re-reached nodes.
- FIXED (QA-001 MEDIUM): Python-fallback recursion-budget segfault — unbounded sys.setrecursionlimit raise (json_depth*4+1000) let the evaluator's per-level visit() recursion smash the 8MB C stack at ~14k JSON depth (CPython ≤3.10 consumes native stack per Python frame; exit 139, faulthandler-pinned). Fix in fhir4ds/fhirpath/duckdb/udf.py `_run_with_recursion_budget`: budgets ≤ _INLINE_RECURSION_LIMIT_MAX (20k) raise in place as before; larger budgets run on a worker thread with a stack sized needed_limit×2KiB (clamped 1MiB–512MiB, threading.stack_size saved/restored); if a worker stack is unsupported, degrade to the inline ceiling so worst case is a clean RecursionError (UDF → [] + debug log), never SIGSEGV. Applies to ALL _eval_with_recursion_budget users, not just repeat. Regression: TestRepeat::test_repeat_extreme_depth_does_not_crash_fallback (depth 6000, crosses the ceiling). Native RepeatDfs verified fine to depth 20k via allow_unsigned_extensions LOAD (beyond that OOM-bound from inherent O(n²) serialized subtrees, not stack-bound); extension binary unchanged (md5 57d0634b6ee6eddee9fc06a1355bef5a).
- QA harness traps: stdlib json.dumps/json.loads on ≥1000-deep structures hit the default recursion limit in the HARNESS, masking UDF results — use the repo's _json_serialize_iterative / string-prefix asserts when probing extreme depths; register_fhirpath() returns native:False in this env (unsigned-extension policy) — to exercise the native engine load the bundled binary with duckdb.connect(config={'allow_unsigned_extensions':'true'}) + explicit LOAD path.

## SOF-VD-07 EXPLORER launch note (2026-08-23)
- Third personality on select.repeat. FIXED (QA-001 HIGH, core FHIRPath, found
  via repeat): the Python-fallback navigation silently DROPPED any element
  whose ONLY key is `extension` (valid FHIR — backbone elements and nested
  Extension wrappers without url), corrupting repeat row counts
  (repeat['extension'] on [a, b, wrapper{extension:[c]}] → 2 rows instead of
  4; repeat→forEach stacks → 0 rows instead of 1). Root cause:
  `apply_parsed_path` (fhir4ds/fhirpath/__init__.py) hid `_field`
  primitive-extension shadow nodes BY KEY SHAPE (`data.keys()==['extension']`).
  Fix: provenance flag `_is_shadow_extension` set at synthesis in
  `create_reduce_member_invocation` (engine/evaluators/__init__.py); both
  top-level filters check the flag. LESSON: never filter synthesized nodes by
  data shape — assert provenance. Native evaluator already returned such
  elements (verified via allow_unsigned_extensions LOAD), so the fix restores
  native/fallback parity; no native/binary change (md5 57d0634b unchanged).
  Regression: fhir4ds/viewdef/tests/unit/test_repeat.py (7 tests). Shadow
  `_birthDate`-style nodes remain hidden (pinned).
- New INTENDED pins: deep-tree repeat is O(n²) per-node subtree serialization
  (inherent to value-based union dedup; correct at depth 3000/6000, 43s/178s);
  3D arrays-of-arrays under repeat yield nothing (list elements filtered,
  dict-only traversal — FHIR never produces them); 12-path repeat unions,
  1000-wide trees, alternating repeat/forEach stacks, contained.ofType inside
  repeat, collection=true per-node multi-values, %rowIndex (0-based, works
  across repeat→forEach stacks), repeat branch inside unionAll, and
  subtree-isomorphism dedup (identical subtree at different depth collapses;
  row counts match union-dedup reference math) all verified end-to-end on
  DuckDB; SQL shape stays flattened CROSS JOIN LATERAL + fhirpath_repeat (no
  recursive CTEs).
- Pre-existing, NOT this launch: 6 failing TestDualEngineParity cases in
  fhir4ds/fhirpath/tests/unit/test_fp18_math_operators.py (uncommitted FP-18
  work; file absent at HEAD db1e4164; native long div/mod parity only).
- Gates fresh: fhirpath+viewdef pytest 1440 passed (6 pre-existing fails
  above); ViewDef conformance 144/144; run_all.py 2832/2832. Probes:
  /mnt/d/fhir4ds/.temp/qa/probe.py.

## SOF-VD-08 SKEPTIC launch note (2026-08-23)
- select.unionAll chunk: 1 HIGH fixed, rest conformant. FIXED QA-001: `_generate_single_resource` (fhir4ds/viewdef/generator.py) suppressed forEachOrNull null-preserved rows across UNION ALL alternatives keyed by resolved PATH — an independent SIBLING select repeating the wrapper's forEachOrNull path lost its null row in non-first alternatives (2 rows -> 1; wrapper+same-path sibling 1 -> 0). Per Process(S,N) step 3 each selection structure emits its own null row; only wrapper copies replicated by `_expand_select_unions` share one. Fix: `_union_origin_id` instance marker on wrappers (survives copy.copy), `_collect_union_wrapper_ids` replaces path tracking. Regression: tests/unit/test_union.py::TestUnionAllForEachOrNullSuppression. Official union.json fixtures never place forEachOrNull as wrapper/sibling of unionAll — this class of bug is fixture-invisible; check the suppression scope whenever touching union expansion.
- Pins re-verified: UNION ALL preserves duplicate rows across branches (no value dedup — unlike FHIRPath `|`); branch schemas must match names+FHIR types+collection flags in order (missing column / reordered / type-changed branches all rejected); empty unionAll array rejected at parse; single-branch legal; nested unionAll-in-unionAll expands correctly; arm model (enclosing columns on branch rows, no standalone base row); enclosing select where filters union rows, branch where is branch-local; all-empty branches suppress parent rows (empty Cartesian part); %rowIndex resets per branch; repeat and forEachOrNull legal inside branches (per-branch null rows); wrapper forEachOrNull+unionAll emits exactly ONE all-null row.
- LOW (unfixed, dead code): `_hoist_nested_unions` and `_build_union_all_query` in generator.py have no live callers — the union path is `_expand_select_unions`/`_expand_select_list_unions`; do not "fix" bugs in the dead path, delete in a cleanup launch.
- Gates fresh: viewdef pytest 1196 (3 new), ViewDef 144/144, run_all 2832/2832 first pass, fhirpath.duckdb_extension md5 57d0634b6ee6eddee9fc06a1355bef5a repo==site-packages (no rebuild).

## SOF-VD-08 HISTORIAN launch note (2026-08-23)
- select.unionAll chunk: 1 more HIGH fixed (depth gap in the SKEPTIC fix). FIXED: a forEachOrNull+unionAll wrapper NESTED below the top-level select list (under forEach, under an outer forEachOrNull, or inside unionAll branches) emitted one null row PER UNION BRANCH instead of exactly one per selection structure — `_collect_union_wrapper_ids` only walked the top-level select list and `_process_selects` did not recurse alias collection. Fix: `_process_selects` now collects paired `foreachornull_wrapper_ids` (the `_union_origin_id`) in lockstep with each forEachOrNull alias at the emission site and recurses both lists; `_generate_single_resource` consumes the pairs; `_collect_union_wrapper_ids` deleted. Bookkeeping is now structurally aligned with SQL emission at any depth.
- Lesson (recurring, 2nd occurrence): unionAll null-row suppression bugs are fixture-invisible (union.json never combines forEachOrNull with unionAll wrappers) — derive expectations from Process(S,N), and whenever touching `_expand_select_unions`/`_process_selects` re-run tests/unit/test_union.py::TestUnionAllForEachOrNullSuppression (now 7 tests incl. nested-depth cases).
- Gates fresh: viewdef pytest 1200 (4 new), ViewDef 144/144, run_all 2832/2832 first pass, fhirpath.duckdb_extension md5 57d0634b6ee6eddee9fc06a1355bef5a repo==site-packages (no rebuild).

## SOF-VD-08 EXPLORER launch note (2026-08-23)
- select.unionAll chunk: 1 HIGH fixed (constants surface, found via unionAll branch probe). FIXED QA-001: backtick-quoted constant references `%`name`` (legal FHIRPath "Environment Variables" spelling) were never substituted — `iter_constant_references` fell through to the backtick skip-region, so both engines silently folded the raw text to an empty collection (NULL columns, where filters dropping ALL rows). Fix in fhir4ds/viewdef/constants.py: `%`name`` now yielded (escape-aware) and substituted like %name; builtin runtime vars normalized to plain %name (engines don't accept backtick form); undefined/non-definable backtick names raise ConstantResolutionError. Regression: tests/unit/test_constants.py::TestBacktickConstantReferences (7 tests).
- Spec ground truth pinned from the RELEASED ig/2.0.0 zip (releases branch): StructureDefinition-ViewDefinition 2.0.0 snapshot has NO `select.where` element — `where` exists only at ViewDefinition root ("filter resources for the view", evaluated against R). fhir4ds's select-level where is a draft-spec extension; its per-iteration evaluation on forEach selects stays fhir4ds doctrine (consistent with the repeat+where pin). Official fixtures never combine element-level where with forEach, nor forEachOrNull with unionAll (fixture-invisible classes, 3rd occurrence).
- EXPLORER pins (all conformant, native==fallback): 24-branch unions preserve duplicates and flatten to a single flat UNION ALL SQL chain; 3-level unionAll-in-unionAll expands per Process(S,N) (plain column branches emit NULL rows — column-empty != row suppression); branch-level forEachOrNull wrappers at depth (under forEach under outer forEachOrNull) each emit their own null row (HISTORIAN fix holds at max nesting); mixed populated/empty branches, where at all scopes with %rowIndex resets per branch, %constants in branches, unionAll sibling to plain nested select cross-joins correctly, %rowIndex in nested-union arms inside forEach stacks resets per arm, contained resourceType mixing routes via branch where.
- NOT A BUG registry: unionAll branches with collection=true and BOTH column.type unset pass schema validation even with heterogeneous runtime element types — the invariant compares declared schemas (sof-js reference impl compares only column NAMES, so fhir4ds remains stricter); explicit mismatched types are rejected.

## Milestone review #10 code-review note (2026-08-23, 50 chunks)
- Delta since #9 reviewed clean: viewdef validation/constants/unionAll-suppression/repeat-budget, fhirpath fallback provenance, CQL query fix. Gates: viewdef pytest 1208, ViewDef conformance 144/144, DQM 47/47 (3rd consecutive green), Message parity 13/13.
- Binary freshness verified BOTH extensions (cql c5b22d58..., fhirpath 57d0634b...): md5 repo==site-packages, binary mtime > newest source; fhirpath binary confirmed current via embedded post-rework native string ("Invalid operands for date/time arithmetic", evaluator.cpp:9651). The SOF-VD-07 SKEPTIC claim "C++ sources ahead of deployed Aug-19 fhirpath binary" is DISPROVEN — no rebuild needed.
- The 7 pre-existing fhirpath parity failures are source-level, not staleness: 5 are PYTHON-FALLBACK temporal±UCUM-quantity validity divergence (fallback valid=True vs native empty/False; test_arithmetic_parity.py:393 — REV-014), 2 are NATIVE std::regex gaps in replaceMatches named-group `${name}` substitution + `$` anchor vs trailing newline (evaluator.cpp:5448-5478 — REV-015). Fix directions: align fallback validity with native fn_dateArith; route/extend native named groups.
- NEW REV-016 (LOW): _run_with_recursion_budget (fhir4ds/fhirpath/duckdb/udf.py:262-311) mutates process-global threading.stack_size()/recursionlimit with lock held only around setters — fine today, revisit if UDF concurrency grows.
- Full findings: fhir4ds-private/docs/prompts/.ai_loop/code_review_findings.md; open items REV-002/003/005/009/010/011/012/013/014/015/016.

SOF-VD-09 HISTORIAN doctrine (2026-08-23): the mixed-context fail-loud guard in
`generator._resolve_environment_path_context` is now SYMMETRIC — a
`%rootResource.`/`%resource.`-PREFIXED expression inside an iterator whose
top-level binary-operator operands (=, &, and, +, ...) reference the CURRENT
FOCUS raises the typed "mixes built-in ViewDefinition contexts"
ValidationError (previously only the reverse ordering errored; the prefix form
silently evaluated focus operands against the ROOT JSON — QA-001 HIGH, e.g.
`forEach: name` column `%rootResource.gender & given.first()` returned
'female' instead of 'femaleAlice'). Guard mechanics:
`_prefix_tail_has_focus_operand` walks the parse AST spine (first child of
every `*Expression` except `InvocationExpression` continues the builtin
continuation; remaining operands are focus-rooted). Deliberately NOT guarded:
function arguments (lambda `$this` scope, e.g.
`%rootResource.name.where(use='official')`) and literal operands
(`%rootResource.gender = 'female'`) — they evaluate against the routed root
input with correct semantics. Indexer `[...]` arguments conservatively fail
loud. Regression class:
TestPrefixMixedFocusOperandSpecSofVd09Historian
(viewdef/tests/integration/test_duckdb.py, native==fallback parity).

SOF-VD-10 HISTORIAN doctrine (2026-08-23): official validator source
(`FHIR/sql-on-fhir.js@main/sof-js/src/validate.js`) settles schema questions
the SD snapshot cannot. Pins: (1) constant items have NO
additionalProperties:false — unknown fields on a constant item are ACCEPTED
(matching official); do not tighten to match column/select/where. (2)
`valueInteger: 3.0` is rejected by fhir4ds although Ajv `integer` accepts
3.0 (JS Number.isInteger); FHIR integer representation forbids the decimal
point — intended stricter boundary. (3) The 2.0.0 SD snapshot has no
select.where/select.repeat elements; both accepted per reference validator +
SOF-VD-05/09 doctrine. (4) Validation order: resource/select required-field
errors surface before name/constant/iterator errors; multi-fault VDs yield a
single typed ParseError. (5) DEFERRED: `Constant.to_dict()` emits
`decimal.Decimal` on the strict JSON-string parse path —
`json.dumps(vd.to_dict())` raises TypeError for decimal constants, and
dict-input vs string-input parses give float vs Decimal. Decimal is the
canonical lossless repr (parse_float=Decimal doctrine; emitting float would
corrupt 18-digit FHIR decimals); callers needing JSON text must use a
Decimal-aware encoder. A future chunk may add a Decimal-aware serializer
API. Probes: `.temp/qa/sof_vd10_historian_2026_08_23/`.

SOF-VD-10 EXPLORER findings (2026-08-23, cross-cutting validation): (1)
RESOLVED QA-001 MEDIUM — adversarial deeply nested select trees (~1000+ deep)
previously escaped `parse_view_definition` as raw `RecursionError` from
`_parse_select` (dict path) or `json.loads` (string path). Fix:
`viewdef/parser.py` `parse_view_definition` is now a wrapper translating
`RecursionError` into a typed `ParseError` ("nested too deeply");
`from_dict` inherits the guard. Regression:
`TestDeepNestingRecursionSafety` (viewdef/tests/unit/test_parser.py; JSON
fixture built by string concat — `json.dumps` of a 2000-deep dict itself
recurses). (2) Decimal doctrine extension (LOW DEFERRED): `to_dict()`
valueDecimal Decimal serialized with `default=str` yields a STRING that
re-parse rejects; round-trip IS stable with `default=float`. Use
Decimal-aware encoders. (3) NOT A BUG Registry: constant name == column name
in one select is ACCEPTED (official validator imposes no cross-field
collision rule; constants are `%name` FHIRPath references, not output
columns); sql-name rejecting `_x`/unicode-first/`ÿname` is spec-correct
(`^[A-Za-z][A-Za-z0-9_]*$`); ALL 62 probed DuckDB reserved words as column
names parse, quote, and EXECUTE end-to-end correctly; resource/fhirVersion
bindings are case- and whitespace-strict (correct — FHIR code bindings);
official v2 examples set resourceType to the full canonical
`https://sql-on-fhir.org/ig/StructureDefinition/ViewDefinition` (parser
requirement verified against ig/2.0.0/Binary-*.json examples). (4) LOW
DEFERRED: nested column faults name element+field+invariant but not the full
select-tree JSON path (Where[i] errors do carry indexes). Fan-out probes:
10000 columns parse+generate 0.94s; 10000 top-level selects 12.1s — no
cliff. Conformance after fix: 2832/2832 (ViewDef 144). Probes:
`.temp/qa/probe_explorer.py`, `probe_exec.py`, `probe2.py`.

## SOF-VD-11 SKEPTIC launch note (2026-08-23)
- View Runner + IG Examples chunk CLEAN (iter 1). Pins: (1) all five published
  sql-on-fhir.org/ig/2.0.0 Binary examples (PatientAddresses,
  PatientAndContactAddressUnion, PatientDemographics, ShareablePatientDemographics,
  UsCoreBloodPressures) parse+generate+execute end-to-end; the
  PatientDemographics page's documented output table reproduces EXACTLY
  (getResourceKey() emits the "Patient/<id>" form). (2) Result-coercion map:
  integer→INTEGER, integer64→BIGINT, decimal→DOUBLE, boolean→BOOLEAN,
  date/dateTime/time→VARCHAR (fixture-pinned — spec_tests assert string
  equality; do NOT cast temporal columns to DATE/TIMESTAMP without a fixture),
  complex types→VARCHAR JSON, collection=true→typed arrays; native==fallback
  identical types AND rows. (3) spec_tests snapshot NO DRIFT as of 2026-08-23
  (22/22 md5 identical to FHIR/sql-on-fhir.js HEAD). (4) FORWARD DRIFT report
  (release-checklist item, do NOT pre-sync): sql-on-fhir-v2 repo HEAD example
  VDs (input/resources/viewdefinition/) switched to resourceType
  "ViewDefinition" + resourceDefinition "...|3.0.0-ballot" (commits
  b5c475b2/ea6a303d, 2026-08-06/07); the published 2.0.0 site still uses the
  canonical-URL form we enforce. (5) QA-001 FIXED: dead mid-session
  `SET allow_unsigned_extensions` retry removed from
  fhir4ds/fhirpath/duckdb/extension.py (DuckDB rejects the SET on a running
  DB, so register_fhirpath(duckdb.connect()) silently downgraded to Python
  UDFs with an INFO log); now a WARNING naming
  duckdb.connect(config={'allow_unsigned_extensions': True}) /
  fhir4ds.connect(). Regression:
  test_extension_parity.py::test_unsigned_bundled_extension_falls_back_with_warning.
  Gates after fix: ViewDef 144/144, master 2832/2832; md5 fhirpath
  57d0634b…, cql c5b22d58… (repo==site-packages, fix is Python-only).
  Probes: .temp/qa/sof_vd11_skeptic_2026_08_23/.

## SOF-VD-11 HISTORIAN launch note (2026-08-23)
- View Runner + IG Examples chunk CLEAN at iteration 1, zero issues (2nd
  consecutive clean personality). New runner-surface pins (probes:
  .temp/qa/sof_vd11_historian/): (1) multi-resource shared `resources` table
  — SQLGenerator(source_table="resources") resourceType filtering correct on
  native AND forced fallback, no cross-type leakage; (2) materialized
  CREATE OR REPLACE VIEW over generated SQL — duckdb_columns() reports
  temporal date columns as VARCHAR (catalog matches the fixture-pinned
  result-description doctrine); same VD executed twice (view overwrite) and
  3 distinct VDs in one session are stable (no session state pollution);
  (3) empty input table → 0 rows with catalog types still declared;
  (4) error boundaries typed: missing select → ParseError, cross-resource
  element-ID column.type → ValidationError at GENERATE time, missing source
  table → CatalogError only at execute; (5) fhir4ds.generate_view_sql public
  surface (str/dict/ViewDefinition, TypeError otherwise, source_table=None →
  pluralized per-type tables) executes end-to-end; (6) all five IG 2.0.0
  Binary examples reproduce row-for-row native==fallback on a multi-resource
  table (Patient/Specimen/non-BP Observation noise present).
- spec_tests snapshot 22/22 md5-identical to FHIR/sql-on-fhir.js HEAD
  7969489 (2026-07-15) — NO DRIFT. WARNING: /mnt/d/sql-on-fhir-v2 is a
  STALE 2024-02 personal fork (its /tests are the known draft-format
  fixtures); upstream drift checks must use
  `gh api repos/FHIR/sql-on-fhir.js/contents/tests/<file>?ref=HEAD`.
- NOT A BUG registry: UsCoreBloodPressures yields 0 rows when Observation
  components' codings lack `system` — the component.forEach where() filters
  empty, and empty Cartesian parts suppress rows per Process(S,N) doctrine.
- Gates: ViewDef 144/144, master 2832/2832; md5 fhirpath 57d0634b…, cql
  c5b22d58… repo==site-packages; no code changes this launch.

## SOF-VD-11 EXPLORER launch note (2026-08-23)
- View Runner + IG Examples chunk CLEAN at iteration 1 (3rd launch; 2 issues fixed).
- QA-001 MEDIUM FIXED (dual-engine divergence): orjson.dumps has a ~127-level
  nesting ceiling and raises TypeError("Recursion limit reached"); inside
  fhirpath_scalar the row-resilient except-TYPEERROR swallowed it, so the Python
  fallback silently returned [] for deeply nested (>=128-level) results while
  native C++ returned the full JSON. Fix: `_json_serialize` in
  fhir4ds/fhirpath/duckdb/udf.py falls back to the existing
  `_json_serialize_iterative` on that specific TypeError. Regression:
  fhirpath/duckdb/tests/integration/test_deep_json_serialization_parity.py.
- QA-002 MEDIUM FIXED (harness): run_all.py's DQM child intermittently crashed at
  `import argparse` (FileNotFoundError from FileFinder on the RELATIVE
  'conformance/scripts' path) because WSL/drvfs can make the cwd momentarily
  unreadable under heavy suite IO (os.getcwd() itself was observed raising in the
  parent). run_all then printed the suite error but summarized a STALE
  dqm_report.json as 47/47 — ALWAYS verify report freshness (mtime +
  conformance.log log_run entry) when a suite reports failed-but-100%. Fix:
  absolute script paths resolved up front + one bounded retry of the transient
  child failure in conformance/scripts/run_all.py.
- Runner pins (native==fallback throughout): 1200-patient mixed-array volume
  through PatientAddresses/PatientDemographics exact rowcounts (forEach drops
  absent/empty; ~0.05 s); UsCoreBloodPressures 150/150 rows with multi-component
  multi-encounter data; unicode/emoji intact; typed decimal accepts 17/38-digit
  JSON integers (DOUBLE coercion; a 38-digit STRING is correctly type-rejected);
  500-deep typed Extension column and 10k-element collection column OK;
  Arrow- and DataFrame-registered input tables execute VDs; fetchall/fetchdf/
  arrow cell-identical; 4 concurrent sessions isolated; absent and JSON-null
  both -> NULL output. NOT A BUG: `type: "json"` is not a valid column type
  (use a real FHIR complex type).
- Gates: viewdef pytest 1231, ViewDef 144/144, master 2832/2832 (DQM log_run
  entry verified fresh); md5 fhirpath 57d0634b…, cql c5b22d58…
  repo==site-packages unchanged (fixes are Python-only). Probes:
  .temp/qa/sof_vd11_explorer/.

## SOF-VD-12 EXPLORER launch note (3rd launch, 2026-08-24)
- EXPLORER probe battery (metadata breadth, profiles, XML, JSON round-trip):
  10/11 probes PASS; prior SKEPTIC/HISTORIAN results all re-verified standing.
- NEW NOT A BUG pins: (1) empty-string canonical in meta.profile is REJECTED
  (FHIR canonical must be non-empty); (2) top-level `ViewDefinition.profile`
  (resource-target profile) NEVER triggers Shareable/Tabular enforcement —
  enforcement reads meta.profile only — and round-trips verbatim.
- Verified: full CanonicalResource metadata breadth round-trips verbatim
  (useContext all 3 value shapes, identifier+assigner, contact+photo, contained,
  nested extensions, mapping incl. comment/commenti); Shareable+Tabular combined
  fire correctly through nested unionAll (both rule errors name the column);
  all 5 official 2.0.0 Binary examples deep-equal round-trip; XML rejected
  with clear ParseError in all forms; profiled VDs execute end-to-end with
  native==fallback parity.
- OPEN ISSUE QA-001 (MEDIUM): Constant valueDecimal round-trip — JSON-string
  input parses decimals to Decimal (parser.py parse_float=Decimal) and
  Constant.to_dict emits it verbatim, so json.dumps(vd.to_dict()) raises
  TypeError; dict-input path yields float (path-dependent output type).
  Fix must respect the Decimal losslessness doctrine (no float coercion).
  Probes: .temp/qa/sof_vd12_explorer/.
- QA-001 RESOLVED (same launch): `types.py::_json_number_value` —
  Constant.to_dict normalizes Decimal to int (integral) / float (exact
  repr round-trip) / typed ValueError (>17 significant digits); dataclass
  .value stays Decimal so generator FHIRPath literal substitution is
  unchanged. Regression tests: TestDecimalToDictJsonSerialization in
  viewdef/tests/unit/test_constants.py. Gates: viewdef pytest 1238/1238,
  ViewDef 144/144, master 2832/2832; extension md5s unchanged.

## SOF-VD-12 EXPLORER launch close-out (2026-08-24)
- CLEAN exit at iteration 1. QA-001 (MEDIUM, Constant valueDecimal JSON
  serialization) RESOLVED + regression-tested; 0 open issues. State pruned,
  details in ARCHIVE_LOG.md; handoffs + GLOBAL_KNOWLEDGE updated.
- Architectural invariant reaffirmed: normalization belongs at the
  serialization boundary (Constant.to_dict), never in the parser; the
  dataclass keeps the lossless Decimal for generator FHIRPath literal
  substitution.

## SOF-VD-13 SKEPTIC launch note (2026-08-24)
- INVARIANTS chunk CLEAN at iteration 1, zero issues. Spec verified against
  build.fhir.org/canonicalresource.html (cnl-0 WARNING `name.matches('^[A-Z]
  ([A-Za-z0-9_]){1,254}$')`; cnl-1 `url matches('^[^|# ]+$')`) and the local
  2.0.0 SD snapshot (which carries NO cnl constraints of its own and NO
  relatedArtifact element).
- Pins: (1) cnl-1 enforced on ViewDefinition.url as a parse ERROR (rejects
  |, #, space, whitespace-only) — intentionally stricter than the base-spec
  WARNING severity, matching the chunk mandate; (2) profile[] and
  meta.profile[] use the permissive canonical check (|version and
  |version|frag permitted; space and empty-string rejected) while url uses
  strict cnl-1 — the split lives in types.py validate_canonical_string vs
  validate_canonical_array; (3) Column.type keeps validate_optional_uri_string
  (relative URIs + element-ID refs + `X|1.0` accepted, whitespace rejected) —
  cnl-1 correctly NOT applied there; (4) cnl-0 on name is warning-only and
  implemented as first-char-upper + 2-255 length, equivalent to the full regex
  because the sql-name parse invariant pre-restricts the charset; (5)
  sql-name enforced on name/Column.name/Constant.name (relatedArtifact is NOT
  a v2 ViewDefinition field — it round-trips verbatim via extra_fields,
  unvalidated, which is correct); (6) column.tag.name namespace warning fires
  only for names without '/' (warning severity); (7) extra_fields is
  repr=False/compare=False — excluded from repr() and ==, and preserves
  unknown top-level keys (text, relatedArtifact, purpose, experimental,
  text.div) byte-identically through to_dict; (8) tagged+profiled VD executes
  with native==fallback identical rows.
- Probes: .temp/qa/sof_vd13_skeptic/ (probe1-3.py).

## SOF-VD-13 HISTORIAN launch note (2026-08-24)
- One MEDIUM issue fixed (QA-001): cnl-1 on ViewDefinition.url was a parse
  ERROR; the official StructureDefinition-ViewDefinition (FHIR/sql-on-fhir-v2
  repo, element ViewDefinition.url) declares cnl-1 severity=warning and the
  sql-on-fhir.js v2.0.0 reference implementation (src/validate.js) does not
  check url characters at all. Demoted to a warning via new
  `types.py:cnl1_url_warning` called from `parser.py:validate_view_definition`;
  whitespace in url remains a lexical `uri` error (`^\S*$`), and empty /
  non-string urls remain errors. `validate_canonical_string` now enforces only
  the uri lexical rule. Unit tests updated (warning + round-trip assertions).
- Verified non-issues: builtin variables (`resource`,`rowIndex`,`ucum`) take
  precedence over same-named constants at execution — matches RI
  `Object.assign(context, envVars)` order; tag.name namespace warnings fire
  per-occurrence (no dedup, deterministic); extra_fields survives multiple
  parse/to_dict round-trips including dataclass mutations in between; text.div
  with XHTML xmlns + entities preserved byte-identically; root unknown keys
  retained while select/column unknown keys rejected (documented §G-3 boundary).

## SOF-VD-13 EXPLORER launch note (2026-08-24)
- Fixed 1 LOW: cnl-0 first-char gate in validate_view_definition was unicode
  isupper(); now ASCII [A-Z] per the spec regex. 2nd LOW (generate_view_sql
  swallows warnings) classified INTENDED — validate_view_definition() is the
  warning-capture API. Details in fhir4ds/viewdef/AGENTS.md. Baseline held:
  ViewDef 144/144, master gate 2832/2832.

## SOF-SQ-01 SKEPTIC launch (2026-08-24) — Analytics Layer SQLQuery/SQLView
- Spec truth: /mnt/d/sql-on-fhir-v2 branch `upstream/sqlquery-view-sources` is the newest branch carrying the SQLView Library profile (branch `upstream/sqlquery` is older, no SQLView). IG canonical = `http://hl7.org/fhir/uv/sql-on-fhir`; LibraryTypesCodes has BOTH `sql-query` and `sql-view`; SQLView fixes type=sql-view, parameter 0..0; SQLQuery `parameter MS` is 0..* (NOT 1..*); contentType binding extensible (out-of-value-set application/sql* codes legal; dialect enforcement deferred to runner); sql-name is ASCII ^[A-Za-z][A-Za-z0-9_]*$.
- Fixed 6 (2 HIGH: official hl7.org/fhir/uv canonicals rejected; SQLView wrongly required type sql-query. 4 MEDIUM: lax base64 (no validate=True); parameter.use silently defaulted though 1..1; sql-name via unicode-accepting isalpha(); missing to_dict roundtrip). Profile recognition now uses canonical frozensets (SQLQUERY/SQLVIEW_PROFILE_CANONICALS) mirroring viewdef/metadata.py dual-form doctrine. Regression tests: fhir4ds/sqlquery/tests/test_sof_sq01_compliance.py (21). Suite 55/55; master gate 2832/2832.
- NOT A BUG Registry: zero-parameter SQLQuery parses fine (spec `parameter MS`, mandate's "1..*" claim is prose error); `upstream/sqlquery` branch's required-binding contentType is superseded by the newer branch's extensible binding.

## SOF-SQ-01 HISTORIAN launch (2026-08-24) — Analytics Layer roundtrip fidelity
- Full FSH differential pass found 5 more divergences past the SKEPTIC's 6: (1 HIGH) to_dict dropped every known-but-unmodeled Library field (description/publisher/extension/identifier/useContext/... ) AND all per-entry extras (content.extension sqlText, relatedArtifact.display, parameter.documentation/min/max) AND meta.versionId/tag — because _KNOWN_LIBRARY_KEYS excluded them from extra_fields while to_dict never emitted them; (1 MEDIUM) to_dict rewrote a declared official hl7.org canonical to the legacy sql-on-fhir.org spelling and dropped type.coding.system/display; (3 LOW) parameter.type accepted any string (now FHIR-primitive-validated via fhir_type_to_duckdb registry at parse time), Library.status 1..1 unenforced, foreign-system type coding accepted (LibraryTypesCodes fixity).
- Doctrine pin: roundtrip fidelity claims must be tested with a FULLY-populated resource diffed key-by-key (top-level AND per-entry), not just the fields a fix touched. to_dict now preserves verbatim meta/type_concept and per-entry extra_fields; the profile canonical is appended to meta.profile only when no recognized declaration exists — never rewritten.
- Fragile spot: all Library test fixtures must carry `status` (base-Resource 1..1 now enforced at parse). sqlquery suite 55→70; master gate 2832/2832.

## SOF-SQ-02 SKEPTIC launch (2026-08-24) — Analytics Layer runner/binding/execution
- Watch-item confirmed (review-55): runner computed the registry DuckDB type but never applied it to temporal params — `'not-a-date'` for a declared `date` bound as VARCHAR and silently returned rows via lexicographic comparison. Fix doctrine: parameter values must be coerced through DuckDB prepared `SELECT CAST(? AS <registry type>)` (type name registry-whitelisted; value never interpolated) so declared types actually reach DuckDB; failures raise `SQLQueryTypeError` with declared-vs-got.
- Type-confusable guards now in `runner._coerce`: Python `bool` rejected for integer/integer64/decimal; signed int32/int64 ranges enforced; `decimal.Decimal` accepted for `decimal`; FHIR partial dates/dateTimes normalized to earliest instant (strict regex) before CAST.
- Cycle detection verified complete: self, mutual-2 (SQLViews), 3-cycle, root-inclusive (chain returning to the executed library's own canonical) — all `SQLQueryCycleError` before execution; diamonds safe. Param path injection-safe end-to-end.
- sqlquery suite 70→89; master gate 2832/2832.

## SOF-SQ-02 HISTORIAN launch (2026-08-24) — Analytics Layer runner coercion closure
- Fixed 1 MEDIUM: Python-native temporal parameter values bypassed declared-type coercion (`_coerce` returned any non-str datetime value verbatim) — `datetime.time` for declared `date` bound as TIME, `datetime.date` for `time`, `datetime.datetime` for `date`. Fix: `_TEMPORAL_KINDS` registry (DATE→date with datetime rejected as higher precision; TIMESTAMP→datetime+date, date accepted as less-precise dateTime at midnight per earliest-instant doctrine; TIME→time) and ALL accepted temporal values now route through the prepared registry CAST. Tests: `TestNativeTemporalKindEnforcement` (5) in fhir4ds/sqlquery/tests/test_integration.py. sqlquery suite 89→94; master gate 2832/2832.
- Fixed 1 LOW (doc): `_bind_parameters` comment claimed prepared SQL only consumes referenced names — false; DuckDB raises InvalidInputException ("excess parameters") for declared-but-unreferenced params. Comment now documents real semantics; behavior unchanged (clear error, no typed-error mandate).
- NOT A BUG Registry (adjudicated against upstream/sqlquery-view-sources StructureDefinition-SQLQuery-notes.md § Query Composition — materialization strategy, cycle handling, dependency depth are explicitly implementation decisions):
  - relatedArtifact label silently overwrites a pre-existing USER view (CREATE OR REPLACE); label vs pre-existing TABLE → DuckDB CatalogException. Both implementation-defined.
  - Mid-chain materialization failure (e.g. invalid dependency SQL) raises a raw DuckDB ParserException and leaves earlier dependency views materialized; no transactional cleanup mandated. Runner docstring documents DROP VIEW cleanup for name release.
  - SQL body referencing an undeclared `$placeholder` → raw DuckDB InvalidInputException (clear message; no typed-error mandate).
- Verified clean (new HISTORIAN probes): mixed dependency graphs (SQLQuery→SQLView→ViewDefinition at depth 2, parallel SQLView deps, JOIN across both, declaration-order materialization); dependency resolving to a SQLQuery Library materializes fine; dialect content (`application/sql;dialect=duckdb`) preserves named-param binding; 120 named parameters through prepared statements; injection payload inert; SKEPTIC fix regression matrix holds.
- Doctrine pin: when tightening parameter-type validation, test BOTH string and Python-native value paths — a guard like `if not isinstance(value, str): return value` re-creates the original hole for native types.

## SOF-SQ-02 EXPLORER runner launch (2026-08-24) — spec-example placeholders, tz determinism
- Fixed 2 HIGH in `fhir4ds/sqlquery/runner.py`: (1) official spec-example `:name` placeholders (sql-on-fhir-v2 examples + SQL Annotations doc) now execute — declared `:name` tokens rewritten to `$name` (skips string literals, quoted identifiers, `--`/`/* */` comments, `::` casts; undeclared colons left verbatim; values always prepared-statement bound). (2) tz-aware native datetime params normalized to naive wall time before the registry CAST — previously bound host-timezone-dependently (10:30+00:00 → 05:30 on tz −5) and inconsistently with the string spelling of the same instant.
- Verified clean: 30-deep SQLView→VD chain, idempotent re-run, rebuild after mid-chain DROP VIEW, interleaved queries on one connection, self/2-cycles, None→SQL NULL, param bound once referenced 3×, emoji round-trip, typed DATE/TIMESTAMP result columns with µs fidelity, multi-statement/DDL bodies execute as authored.
- NOT A BUG: named placeholders only (positional/mixed `?` bodies surface raw engine errors); duckdb 1.5.2 CAST('24:00:00' AS TIME) returns str (engine quirk).
- sqlquery suite 102/102; master gate 2832/2832.

## SOF-SQ-03 QA launch (2026-08-24, SKEPTIC) — integration seams
- Verified PASS end-to-end on real DuckDB: one-level and two-level chains, cycle detection, error transitivity (SQLError→SQLOnFHIRError→ValueError), one-way dependency (viewdef never imports sqlquery), public API exports/docstrings.
- Known Fragile: runner `_materialize_one` — resolver returns of parsed SQLQuery/SQLView objects rejected (only ViewDefinition isinstance handled); duckdb Catalog/Binder exceptions from CREATE VIEW during materialization escape the typed hierarchy entirely; ambiguous dicts (resourceType='Library' + select/resource keys) misroute to viewdef parser; parameter.name lacks sql-name validation (labels have it).
- SOF-SQ-03 fixes (same launch): runner `_materialize_one` now delegates shape handling to `_resolve_view_sql` (parsed SQLQuery/SQLView objects accepted; ambiguous resourceType='Library'+select/resource dicts rejected typed); ALL post-resolver failure paths (parse, dialect selection, SQL generation, CREATE VIEW) wrapped into SQLQueryMaterializationError with label+canonical context — SQLQueryCycleError and nested MaterializationErrors re-raise untouched; validator enforces sql-name on parameter.name. Tests: TestSofSq03IntegrationSeams (7) in sqlquery/tests/test_integration.py. sqlquery suite 102→109; master gate 2832/2832.

## SOF-SQ-03 QA launch (2026-08-24, HISTORIAN) — integration seam regression audit
- All 4 SKEPTIC fixes re-verified regression-free, including new angles: all four resolver shapes mixed in ONE dependency list, SUBCLASS instances of parsed objects, two-level nested resolver failures (inner label+canonical surfaced, __cause__ preserved), parse→to_dict→re-parse byte-stability, native C++ vs Python-fallback parity (identical rows), `import *` lands exactly `__all__` (26 names), DependencyResolver runtime alias documented. Locked in TestHistorianLaunch (4 tests); sqlquery 109→113; master gate 2832/2832.
- Fixed (LOW): SQLQueryRunner.__init__ resolver docstring understated the post-SKEPTIC resolver contract (omitted parsed SQLQuery/SQLView objects) — when a fix changes an accepted-input contract, update adjacent docstrings in the same commit.
- INTENDED (registry, fhir4ds/sqlquery/AGENTS.md): main SQL-body engine errors (duckdb Binder/Catalog on the author's own SQL) escape raw by design — no mandate item covers them and the threat model excludes author-controlled SQL; dependency-materialization errors remain typed.

## SOF-SQ-03 QA launch (2026-08-24, EXPLORER — campaign FINAL) — integration boundary sweep
- Zero defects; 10 boundary areas verified end-to-end on real DuckDB (probes .temp/qa/explorer_probe1.py, explorer_probe2.py): diamond dependency graphs (per-edge re-materialization, idempotent, rows correct from both consumers), depth-5 mixed SQLQuery→SQLView→SQLQuery→SQLView→VD chain, main body combining dependency view + :param, dependency label colliding with the SOURCE table name (typed SQLQueryMaterializationError, table NOT clobbered), parameters do NOT flow through materialized dependency views (typed error at CREATE VIEW; SQLView profile forbids params), unicode/emoji SQL-body literals byte-correct + unicode labels rejected per ASCII sql-name, interleaved runner instances on one shared connection, 3-level nested failure surfaces the INNERMOST label+canonical with __cause__ chain, native-vs-fallback parity on the depth-5 chain, parameter name == dependency label (no collision).
- INTENDED registry additions in fhir4ds/sqlquery/AGENTS.md: diamond non-dedup (documented statelessness) and params-through-views semantics.
- sqlquery+viewdef 1354 passed; master gate on final tree recorded in .ai_loop launch handoffs; binary md5s repo==site-packages (fhirpath 57d0634b…, cql c5b22d58…).

## 0.0.12 Evolution Campaign — Domain 6 SKEPTIC launch (2026-08-24, iter 1)
- Probed FHIRDataLoader/resources-table contract (fhir4ds/cql/loader/fhir_loader.py) with 14 hypotheses on live DuckDB 1.5.2; probes in fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/iter1_domain6_skeptic_probe.py.
- Known Fragile Areas (new, OPEN): (QA-001 HIGH) `_extract_patient_ref` takes the last path segment of ANY subject/patient/beneficiary ref with no target-type check — Condition subject Group/g7 yields patient_ref 'g7', and cte_builder.py:278 emits patient_ref AS patient_id, fabricating phantom patients in patient-context measures. (QA-002 MEDIUM) resolve() macro mis-segments versioned refs 'Patient/123/_history/2' (id='2', type='_history' -> NULL, silent drop). (QA-003 MEDIUM) load_file/load_ndjson reject UTF-8-BOM files (RFC 8259 permits ignoring BOM; Windows exports). (QA-004 LOW) list-valued patient refs (Appointment.patient 0..*) -> patient_ref NULL, resource drops from patient context. (QA-005 LOW) load_bundle silently skips entry.resource={} and lacks per-entry index attribution (NDJSON path has per-line attribution).
- NOT A BUG Registry: resolve() on bare ids ('123') matches any resourceType with that id (LIMIT 1 arbitrary) — bare ids are not valid FHIR relative references; the macro's bare-id support is a deliberate convenience. Bundle.type full 1..1 + binding validation, FHIR id pattern enforcement (underscore/65-char rejected), NaN/Infinity rejection with line attribution, strict NDJSON no-partial-load, >1MB resource round-trip, duplicate (id,type) reload idempotency (delete-before-insert, last-write-wins) — all verified PASS.

## 0.0.12 Evolution Campaign — Domain 6 SKEPTIC fixes (2026-08-24, iter 1)
- All 5 QA findings RESOLVED in fhir4ds/cql/loader/fhir_loader.py, verified by 13 new tests in cql/tests/unit/test_fhir_loader.py (72/72), loader/ 216/216, master gate 2832/2832.
- QA-001 (HIGH): _extract_patient_ref now type-checks reference targets — patient_ref only for Patient-typed refs (relative, absolute, versioned-stripped) and urn:uuid bundle-local refs; Group/Location/bare-id/logical refs → NULL (was: last path segment of ANY ref → phantom patients downstream).
- QA-002: resolve() macro strips /_history/{vid} (regexp_replace) before segment matching; versioned refs resolve to current resource (was NULL).
- QA-003: load_file/load_ndjson decode utf-8-sig (BOM tolerated per RFC 8259 §8.1).
- QA-005: load_bundle validates entry resources with Bundle.entry[N] attribution; {} resources now raise (was silent skip).
- Behavior changes to carry into 0.0.12 release notes: bare-id refs and non-Patient subject refs no longer populate patient_ref; versioned references resolve; BOM files accepted; empty bundle entry resources rejected with index.

## 0.0.12 Evolution Campaign — Domain 6 HISTORIAN (2026-08-24, iter 2)
- Spec-walk of loader vs FHIR R4 Bundle/NDJSON: CRLF/blank lines/no-trailing-LF, request-only entries, contained resources, nested bundles, batch-response payloads, non-string resourceType — all verified. NOT A BUG Registry additions: nested bundles stored as-is (spec silent); batch-response OperationOutcome payloads load as data (data-vehicle doctrine); urn:uuid fullUrl resolution for id-less transaction entries not supported (identity model is (id, resourceType)) — QA-008 DEFERRED known limit.
- QA-006 (HIGH) RESOLVED: FileSystemSource._raw_fhir_patient_ref_sql now implements the shared Patient-typed patient_ref doctrine (was: untyped last-segment — phantom patients via FileSource raw-FHIR path). Tests: TestRawFhirPatientRefDoctrine. Patient-ref doctrine table (QA-007 DEFERRED note): loader Python (typed+versioned+urn:uuid+list-form) and filesystem SQL (typed+versioned+urn:uuid) are aligned; mongo (typed relative+absolute) and hapi (typed relative) are stricter — align edge semantics on next touch.
- iter-1 fixes regression-verified (5/5 matrix PASS). Validation: filesystem 41/41, sources+loader 294/2 skipped, master gate 2832/2832.

## 0.0.12 Evolution Campaign — Domain 6 EXPLORER (2026-08-24, iter 3)
- 4 fixes in fhir_loader.py (tests +4, 76/76; loader+sources 438/2; gate 2832/2832): QA-009 load_directory case-insensitive suffix matching; QA-010 OSError in directory skip-net (unreadable file no longer aborts bulk load with partial state); QA-011 RecursionError → ValueError for deep nesting; QA-012 serializer message names NaN/Infinity and circular refs.
- NOT A BUG Registry: duplicate JSON keys last-wins (universal stdlib behavior); post-load dict mutation inert (serialize-at-load); 10MB+ strings round-trip; JSON-array NDJSON line rejected with line attribution.

## 0.0.12 Evolution Campaign — Domain 7 SKEPTIC (2026-08-24, iter 4)
- QA-013 (MEDIUM, PERF) RESOLVED: load_resources used per-row executemany (10k rows = 4.08s insert vs 0.03s python build). Fix: Arrow register + INSERT SELECT bulk path for dedup DELETE (semi-join) + batch INSERT, executemany fallback on ImportError (mirrors load_valuesets doctrine). 25k fresh 18.6s→0.27s; reload →0.14s. Tests: bulk/fallback/NULL-typing in test_fhir_loader.py.
- Verified CLEAN: scaling linear 1k-25k (no cliff), no tracemalloc leak (3x5k cycles), 4-thread concurrent loaders clean, concurrent same-conn construction clean, resolve() decorrelated by DuckDB (10k refs in 0.01s).

## 0.0.12 Evolution Campaign — Domain 8 SKEPTIC (2026-08-24, iter 7)
- QA-014 (MEDIUM, API_CONTRACT) RESOLVED: evaluate_measure on a bare duckdb connection raised raw CatalogException (fhirpath_date leak) for date-dependent libraries — docstring silent on UDF precondition. Fix: pre-flight duckdb_functions() probe → RuntimeError with create_connection()/register(conn) remedies. Tests: cql/tests/integration/test_udf_registration_guard.py.
- NOT A BUG Registry: ViewDefinition top-level name is 0..1 (published IG StructureDefinition) — nameless VDs parse; name validated (sql-name) when present. dqm/hapi_materialization `except…pass` on value.item() is duck-typing; core.py remove_function swallow is expected-when-absent cleanup.

## 0.0.12 Evolution Campaign — Domain 8 HISTORIAN+EXPLORER (2026-08-24, iter 8-9)
- QA-015 (MEDIUM) RESOLVED: output_columns unknown definition names now ValueError with available list (was raw CatalogException leak). QA-016 (MEDIUM) RESOLVED: unknown parameter names now TypeError listing declared params (was silent CQL-default fallback → wrong measure results from typos). Tests in cql/tests/integration/test_udf_registration_guard.py.
- DOCTRINE (NOT A BUG Registry, controlling test test_evaluate_measure_missing_udf_catalog_error_is_not_rewritten): evaluate_measure supports BARE duckdb connections (FakeTranslator test pattern); missing-UDF CatalogExceptions surface raw mid-evaluation by design. A pre-flight registration guard was attempted and reverted (iter 9 Recovery Gate).
- NOT A BUG: fhirpath.evaluate(None, expr) → [] (null→empty propagation); fhirpath_is_valid is a SQL UDF not a Python export; translate_cql takes TEXT not paths.

## 0.0.12 Evolution Campaign — Domain 9 SKEPTIC (2026-08-24, iter 10)
- MT-008 / QA-017 (HIGH) RESOLVED (root fix, 2 parts): (1) quantity Min/Max aggregate dispatch now attaches the row-path arg_min/arg_max audit twin — evidence names the winning resource (e.g. Observation/obs-low) not the quantity value; (2) dispatched quantity aggregates carry result_type='Quantity' so CTE-reference comparisons route through quantity_compare — `MinBP < 140 'mmHg'` was False (TRY_CAST→NULL), now True. cql unit+integration 1865/0 (first fully green run); gate 2832/2832. Tests: TestMinMaxAttribution + TestMinMaxQuantityEvidenceEndToEnd (e2e evidence).
- Follow-up flag for code review: sibling quantity aggregates (Sum/Avg) may need the same result_type marking.

## 0.0.12 Evolution Campaign — Domain 9 HISTORIAN (2026-08-24, iter 11)
- QA-018 (MEDIUM) RESOLVED: audit_mode=full multi-definition output violated one-row-per-patient (evidence JOIN fan-out cartesian; 2 obs x 2 defs = 4 rows). Fix: per-patient aggregation in _wrap_definition_cte evidence branch (ANY_VALUE result, list_distinct flatten evidence). Evidence now unions per-patient (both Observations cited). Tests: TestAuditEvidenceRowContract. cql 1867/0; gate 2832/2832.
- Verified: Sum/Avg quantity result_type coverage from iter-10 fix; exclusion evidence causality (target+operator present, 'absent' sentinels for gaps).

## 0.0.12 Evolution Campaign — Domain 11 SKEPTIC+HISTORIAN (2026-08-24, iter 16-17)
- Domain 11 SKEPTIC: full documented-surface battery CLEAN (no README-vs-behavior drift; directives shorthands mapped: connect→create_connection, population_sql→translate_library_to_sql).
- QA-019 (LOW) RESOLVED: evaluate_measure parameters type guard (was raw AttributeError on non-dict). Test: test_parameters_type_guard. 58 passed; gate 2832/2832.

## 0.0.12 code review (2026-08-24, full-diff, post-evolution-campaign)
- CLEAN_WITH_NOTES. Evolution-campaign diff (loader/filesystem/cql-init/translator/cte_manager + tests): SQL-injection clean (parameterized + quoted identifiers + static SQLRaw), error hygiene clean, Arrow bulk doctrine-consistent, model-knowledge within carve-outs (REV-002-family note). REV ledger re-verified: 11 open hardening items carried unchanged (REV-002/003/005/009-016), resolved items symbol-verified. Clobber spot-check: all campaign fix symbols present. Gate 2832/2832; CQL suites 1867/0. Findings: code_review_findings.md.

## 0.0.12 pre_release (2026-08-24) — GO
- Version bumped 0.0.11→0.0.12 (pyproject + root + all 6 subpackage constants; test_version 2/2). Wheel rebuilt: medterm4ds bound ships exactly (>=0.0.2,<0.0.3 both extras); extension md5s repo==wheel==site-packages (fhirpath 57d0634b, cql c5b22d58); clean-venv install smoke + pip check clean; register flags both True; native function proofs pass. Conformance 2832/2832. Report: release_readiness_report.md. WASM/website assigned to docs_audit per directives.

## 0.0.12 docs_audit + scribe (2026-08-24) — PIPELINE COMPLETE
- docs_audit: 4/4 notebooks executed clean against the 0.0.12 wheel; all stale versions fixed (notebooks, PRODUCT_VERSION, demo.spec.ts, notebooks.md); releases.md v0.0.12 section (4 pillars + campaign fixes, 2832 baseline); wasm-demo rebuilt with 0.0.12 wheel (stale 0.0.10 removed) and copied to static/wasm-app; typecheck + build clean; micropip deps=False rule verified intact; draft-page link softened (decision for Joel: publish cql-tests-runner-facade?). Report: docs_audit_report.md.
- scribe: 3-commit draft in .temp/draft_commit.txt (campaign+medterm / evolution fixes / release bump+docs).
- FULL PIPELINE COMPLETE: evolution (21 iters, CLEAN) -> code_review (CLEAN_WITH_NOTES) -> pre_release (GO) -> docs_audit (READY) -> scribe. No commits made (Joel commits).
