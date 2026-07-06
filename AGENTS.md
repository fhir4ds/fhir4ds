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

CQL-01 EXPLORER found a fragile `Any` materialization boundary. Scalar
primitive definitions asserted `as Any` or `as System.Any` must remain
patient-scalar `value` projections in `definition_meta`; final population SQL
must not reclassify them as resource-shaped CTEs and select `.resource`.

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

**Hardened in CQL-13 SKEPTIC (2026-Q2).** Date/time `duration between` with
uncertain operands must cap the high end at the requested precision, unlike
`difference between` which counts crossed boundaries. The current CQL Reference
example `months between @2012-01-02 and @2012` is `Interval[0, 10]`; the
corresponding month `difference` remains `Interval[0, 11]`. Keep Python
fallback, native-loaded registration, and no-Python/browser-style C++ helper
tests together for `cqlDurationBetween` / `cqlDifferenceBetween`.

**Hardened in CQL-14 EXPLORER (2026-Q2).** Date/DateTime/Time public quantity arithmetic helpers are row-resilient at malformed Quantity boundaries. Python fallback `dateAddQuantity` and `dateSubtractQuantity` must match no-Python/browser-style C++ behavior by returning SQL NULL for malformed JSON, missing `value`, null `value`, string or Boolean `value`, non-finite values, unsupported units, and huge values. Do not treat missing `value` as zero or coerce numeric strings. Valid arithmetic overflow remains an official invalid-expression error path for translated CQL conformance.

**Verified in CQL-14 SKEPTIC (2026-Q2).** Current-clock and precision Date/Time operators need cross-runtime coverage even when no remediation is required. Keep translated `Now() = Now()`, `Today() = Today()`, `TimeOfDay() = TimeOfDay()`, time-only `same` comparisons, invalid `week` precision NULLs, timezone-normalized same-second checks, null-gap Time constructor behavior, and partial DateTime month subtraction aligned across forced Python, native-loaded, and no-Python/browser-style C++ surfaces.

### CQL Interval Operator Boundaries

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

### FHIRPath Expression-Parameter Scope Restoration

**Fixed in milestone review-5 remediation (2026-05-16).** Every expression-parameter function must restore transient scope after evaluating criteria/projection expressions. Python `all(criteria)` must save and restore `$index`, matching `where()`/`select()`/`repeat()`. Native C++ `where(criteria)` must save and restore `defined_variables_` in addition to `chain_defined_vars_` and `index_context_`; `defineVariable()` inside criteria must not leak into subsequent chained expressions. Regression coverage lives in `test_existence_parity.py` and `test_filter_projection_parity.py`.

### FHIRPath Tree Navigation Nulls and Trace Projection

**Fixed in FP-12 SKEPTIC tree/utility audit (2026-05-17).** `children()` and `descendants()` expose child nodes, including JSON null-valued children; ordinary field navigation may still skip nulls. Native UDF result materialization must preserve nulls with an owned sentinel after `yyjson_doc_free()` so `fhirpath_json(..., 'children()')` can emit JSON `null` and `count()` sees the child-node item. `trace(name, projection)` must return the original input unchanged while logging the projection result, with `$this` restored after projection evaluation. Regression coverage lives in `test_tree_utility_parity.py`, `test_new_functions.py`, and `extensions/fhirpath/test/sql/fhirpath.test`; after native changes, rebuild and copy the bundled `fhirpath.duckdb_extension`.

### FHIRPath Current-Time Function Determinism

**Fixed in FP-12 EXPLORER utility audit (2026-05-16).** FHIRPath §5.9.2 requires `now()`, `today()`, and `timeOfDay()` to return the same value regardless of how many times they are evaluated within one expression. Native C++ must cache one timestamp per `Evaluator::evaluate()` call; do not call `time(nullptr)` separately in each function branch. Long expressions can otherwise cross a second boundary and make `now() = now()` false. Regression coverage lives in `fhir4ds/fhirpath/duckdb/tests/integration/test_tree_utility_parity.py`; after native changes, rebuild and copy the bundled `fhirpath.duckdb_extension`.

### FHIRPath Conversion Singleton and Type Tables

**Fixed in FP-06 SKEPTIC conversion audit (2026-05-16), tightened in review-10 remediation (2026-05-17).** Integer conversion is not decimal truncation: `toInteger()` and `convertsToInteger()` accept Integer, Boolean, and strings matching `(+|-)?\d+`, but Decimal inputs such as `1.0` must return empty/false. Do not validate integer strings with APIs that skip whitespace, such as `std::stoll`, unless an exact regex-style guard runs first. Conversion-section functions, including `iif()`, must enforce singleton input before evaluating arguments; DuckDB public wrappers should convert these semantic errors to empty/NULL outside strict mode. Direct helper APIs in `fhir4ds/fhirpath/duckdb/functions/conversion.py` must use the same Boolean, Date, Time, DateTime, and Quantity conversion tables as the public/core path; do not strip whitespace, truncate malformed DateTime strings, accept timezone-bearing Time strings, or ignore incompatible target units. Regression coverage lives in `test_conversion_parity.py`, `test_operator_parity.py`, and `test_conversion.py`; after native changes, rebuild and copy the bundled `fhirpath.duckdb_extension`.

### FHIRPath Direct String Helper Semantics

**Fixed in FP-09 HISTORIAN string-search audit (2026-05-16).** Public DuckDB UDFs and the core Python fallback agree for §5.6.1-§5.6.5, and direct helper functions in `fhir4ds/fhirpath/duckdb/functions/string.py` must also preserve FHIRPath singleton String semantics. Do not coerce non-string helper input with `str(value)`, and keep `substring(start == length)` empty per the normative example `'abcdefg'.substring(7, 1) // { }`.

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

