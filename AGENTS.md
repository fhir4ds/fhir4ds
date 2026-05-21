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

---

## Development Workflow
...
- **Benchmarks:** `benchmarks/`
- **Official Tests:** `tests/data/` (Heavy datasets and submodules)

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

CQL Date/DateTime/Time constructors are public temporal boundaries, not string
formatting shortcuts. Runtime constructor output must be validated by the same
temporal parser path used by public helper UDFs so invalid dynamic values such
as `Date(year from @2024-01-01, 13)`, `DateTime(..., hour: 24)`, or timezone
offsets beyond `+/-14:00` return SQL NULL instead of leaking malformed lexical
values. `Time(hour, minute, second, millisecond)` preserves CQL time string
precision including the `T` marker and milliseconds. Time-only quantity
arithmetic is clock-domain arithmetic: preserve input precision and keep native
C++ and Python fallback behavior aligned across midnight.

CQL `ToQuantity` has multiple public shapes: strings such as `5 'mg'`,
numeric Integer/Long/Decimal values that become unit `1`, and internal
JSON-shaped Ratio values that divide numerator by denominator. Native-loaded
connections must shadow the legacy C++ `ToQuantity(VARCHAR)` with the Python
conformance helper until the C++ surface implements the same overloads.
`ConvertsToQuantity` over JSON-shaped values must require a finite Decimal
`value`, not just the presence of a `value` key.

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

CQL interval operators must preserve Quantity shape at interval boundaries.
Do not reduce Quantity bounds or points to bare numeric values before
comparison; `Interval[1 'g', 2 'g'] contains 1500 'mg'` depends on the same
unit-aware comparison surface as ordinary Quantity ordering. Interval-valued
set-operation outputs such as `intervalExcept`, `intervalIntersect`, and
`intervalUnion` remain interval expressions for downstream `contains`,
`includes`, equality, and precision operators; translator dispatch must not
fall through to generic DuckDB list/string functions for nested interval
composition.

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

**Hardened in milestone review-30 (2026-Q2).** Boundary helper and temporal helper validation applies to direct public UDF calls, not only translated CQL. Reject malformed Date/DateTime bodies, non-finite numeric text, impossible offsets, colonless offsets, and unbounded exponent expansion. `Now()` must normalize DuckDB `CURRENT_TIMESTAMP` offsets from `-HH` to `-HH:00` before strict timezone parsing. Native `quantityToInterval` and date quantity helpers return NULL for invalid/empty/huge Quantity input, and date quantity arithmetic preserves date-only precision. Native `ToQuantity` numeric and Boolean overloads are required for C++-only/browser parity. Quantity/scalar `*` and `/` over FHIR `value[x]` must use `fhirpath_number`/`TRY_CAST`, not plain `CAST`; `Power()` and `^` route through `mathPower` with an outer numeric `TRY_CAST`.

**Hardened in CQL-11 SKEPTIC (2026-Q2).** Arithmetic Part 2 public helpers must be parity-tested across native-loaded DuckDB registration, forced Python fallback registration, and C++-only/browser-style surfaces where functions/macros are registered. CQL `Round` ties round toward positive infinity, so direct `mathRound` must use `floor(x * 10^precision + 0.5)` behavior even for negative ties. `Power` and direct `mathPower` return NULL for NaN, infinity, or unrepresentable results. Quantity `mod` and truncated `div` with compatible units convert the right operand into the left operand unit before arithmetic and preserve the left operand unit. Direct `predecessorOf`/`successorOf` helpers return NULL at public SQL boundaries for row resilience, while translated static temporal underflow/overflow remains an invalid CQL expression for official conformance. Maximum/minimum `DateTime` and `Time` literals retain the CQL `T` marker and millisecond precision.

**Hardened in CQL-11 HISTORIAN (2026-Q2).** Arithmetic Part 2 dynamic FHIR `value[x]` operands must use typed numeric projection (`fhirpath_number`) for numeric-only operations such as `div`, `Power`/`^`, `Round`, and `Truncate`; `fhirpath_text` plus SQL coercion can both binder-fail and incorrectly accept `valueString`. Apply CQL representational boundary rules in translation for static min/max cases: `-(minimum Integer)` and `-(minimum Long)` are NULL, `-(minimum Decimal)` is the positive maximum Decimal, and Decimal predecessor/successor at min/max is NULL. Static DateTime literal boundary underflow/overflow is invalid just like constructor boundary cases. Public helper parity also covers invalid time strings, unrepresentable `mathPower`, and DateTime precision with `+/-HH:MM` timezone suffixes, whose digits do not count as precision.

**Hardened in CQL-11 EXPLORER (2026-Q2).** CQL Arithmetic Part 2 direct SQL macros are public compatibility surface: `Div(x, y)` must truncate toward zero for Decimal operands and return NULL on zero divisor. `minimum DateTime` and `maximum DateTime` use the official XML UTC boundary suffix `Z`. Predecessor/successor over Date, DateTime, and Time values is precision-aware and preserves lexical precision (`YYYY`, `YYYY-MM`, `YYYYT`, `YYYY-MMT`, `YYYY-MM-DDTHH`, `T12`, `T12:30`, etc.). DateTime marker forms are DateTime values, not numeric text. Mixed scalar/Quantity `mod` and `div` must convert scalar operands to unit `1` Quantity JSON before UDF dispatch; never emit `parse_quantity(<number>)`.

**Hardened in CQL-14 EXPLORER (2026-Q2).** Date/DateTime/Time public quantity arithmetic helpers are row-resilient at malformed Quantity boundaries. Python fallback `dateAddQuantity` and `dateSubtractQuantity` must match no-Python/browser-style C++ behavior by returning SQL NULL for malformed JSON, missing `value`, null `value`, string or Boolean `value`, non-finite values, unsupported units, and huge values. Do not treat missing `value` as zero or coerce numeric strings. Valid arithmetic overflow remains an official invalid-expression error path for translated CQL conformance.

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

### CQL String Operator Boundaries

**Hardened in CQL-12 SKEPTIC (2026-Q2).** CQL string operators need explicit null/boundary handling across translated SQL, Python fallback registration, native-loaded DuckDB registration, and no-Python/browser-style macro surfaces. `Combine` and `CombineSep` return NULL when the non-null filtered list is empty. `Substring` returns NULL for null/negative/at-or-past-end starts and null/negative lengths; do not inherit DuckDB's empty-string slicing for invalid CQL boundaries. `StartsWith` and `EndsWith` are exact prefix/suffix checks, so translated CQL must call the public macros rather than `LIKE`; `%` and `_` are data, not wildcards. String bracket indexing routes through the public `Indexer` macro instead of list extraction so at-end/out-of-range string indexers return NULL. Deprecated Python string UDFs should return NULL for null search operands or invalid substring inputs instead of raising.

**Hardened in CQL-12 HISTORIAN (2026-Q2).** CQL regex-backed string operators use single-line mode: unescaped `.` matches newline, and `^`/`$` provide whole-string anchoring when needed. DuckDB `Matches` and `SplitOnMatches` macros must pass regex option `s`, and `ReplaceMatches` must use `gs` for global single-line replacement while preserving CQL `$1` capture references and escaped literal dollars. Deprecated `stringMatches` should use `re.DOTALL` and return NULL for null patterns; deprecated string UDFs should keep row-level NULL resilience for null operands.

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

### CQL Structural Type Operators

**Fixed in CQL-05 SKEPTIC/HISTORIAN/EXPLORER structural audit (2026-05-17).** CQL `is`, `as`, and `convert` must validate unknown structural targets and treat `List<T>`, `Interval<T>`, `Choice<T...>`, and `Tuple { ... }` as first-class type specifiers. Static aliases should preserve exact List, Interval, Ratio, Date, DateTime, Time, and Tuple identity. `as Quantity` over FHIR values must preserve `parse_quantity`/Quantity shape for downstream unit-aware comparisons. Numeric fallback for optimized quantity CTEs must not ignore incompatible units when the dynamic side is a JSON Quantity object. `Message(..., 'Error', ...) as Interval<T>` preserves `CQLMessage`, dynamic `as Concept`/`as Code` keeps runtime CodeableConcept/Coding matching, and SQL CASE sources produced by choice `as` casts remain valid FHIRPath property-navigation sources. `Children()`/`Descendants()` use internal typed transport for primitive child items, including temporal and Long values, so downstream `is`/`as` and `List<T>` checks do not coerce strings or erase identity. `convert <Quantity> to String` shares the `QuantityToString` path used by `ToString(<Quantity>)`; `convert List<Code> to Concept` and `convert Concept to List<Code>` are registered DuckDB UDF surfaces. Forced Python fallback tests must directly register Python FHIRPath UDFs, assert `fhirpath_predicate` is absent, and keep choice-field `value.is/as(Type)` parity with native execution. `as Concept` over FHIR resource properties should preserve resource/path information for value-set and coding matching.

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
