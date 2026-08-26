# FHIR4DS Comprehensive Architecture Audit Report
## 2026-Q2 Code Review & Design Audit

**Date:** 2026-04-10
**Scope:** All subprojects in `fhir4ds/`, `extensions/`
**Test Baseline:** 6,465 passed | 4 failed (pre-existing) | 64 skipped

---

## Executive Summary

| Subproject | CRITICAL | HIGH | MEDIUM | LOW | Total |
|------------|----------|------|--------|-----|-------|
| fhirpath (core) | 4 | 10 | 12 | 6 | 32 |
| fhirpath/duckdb | 2 | 4 | 6 | 5 | 17 |
| cql/translator | 10 | 49 | 59 | 42 | 160 |
| cql/duckdb | 2 | 5 | 9 | 5 | 21 |
| viewdef | 3 | 7 | 10 | 6 | 26 |
| dqm | 3 | 8 | 8 | 5 | 24 |
| extensions/fhirpath (C++) | 2 | 4 | 5 | 3 | 14 |
| extensions/cql (C++) | 0 | 3 | 5 | 3 | 11 |
| **TOTAL** | **26** | **90** | **114** | **75** | **305** |

### Systemic Themes (Cross-Cutting)

1. **Pure AST Pipeline Violations** (~20 sites): `to_sql()` called mid-pipeline, `SQLRaw` with f-string SQL, regex on serialized SQL. Concentrated in `cql/translator/expressions/`.
2. **Silent Fallbacks Masking Bugs** (~40 sites): `except Exception`, `getattr(…, {})`, default returns, swallowed errors. Violates Fail Fast invariant.
3. **`LIMIT 1` Instead of Singleton Semantics** (13+ sites): Silently picks arbitrary row instead of enforcing CQL `singleton from` semantics.
4. **CQL Three-Valued Logic Violations** (~10 sites): Functions return `False`/`0` instead of `None`/`NULL` for unknown/null inputs, corrupting boolean logic chains.
5. **Mega-Functions** (8 methods >100 lines): `_translate_query` is 1,363 lines. Root cause of duplicated logic and deep nesting.
6. **Thread Safety** (~8 sites): Shared mutable globals, LRU caches without locks, module-level singletons.
7. **Hardcoded Domain Knowledge** (~15 sites): FHIR type hierarchies, resource type lists, LOINC codes, profile URLs embedded in core logic.

---

## Prioritized Remediation Plan

### P0: CRITICAL Safety & Correctness (Fix First)

#### P0-1. C++ JSON Injection via Factory Methods
- **File:** `extensions/fhirpath/src/fhirpath/evaluator.cpp:4692-4807`
- **Background:** Factory methods (`Coding`, `Extension`, `Identifier`, `Address`) construct JSON via raw string concatenation. User-controlled strings containing `"`, `\`, or other JSON-special characters produce malformed or exploitable JSON.
- **Fix:** Use yyjson_mut_doc API for all JSON construction.
- **AC:** No raw string concatenation for JSON in evaluator.cpp. Fuzz test with special characters passes.

#### P0-2. C++ Regex Denial of Service (ReDoS)
- **File:** `extensions/fhirpath/src/fhirpath/evaluator.cpp:28-39`
- **Background:** `matches()`, `replaceMatches()` compile user-supplied regex patterns via `std::regex` with no length limit, no timeout, and unbounded cache growth.
- **Fix:** (a) Limit pattern length to 1024 chars. (b) Cap thread-local regex cache to 256 entries. (c) Consider RE2 for linear-time matching.
- **AC:** Patterns >1024 chars return error. Cache has bounded size. Pathological patterns don't hang.

#### P0-3. CQL `in_valueset` Returns False Instead of NULL
- **File:** `fhir4ds/cql/duckdb/udf/valueset.py:407-434`
- **Background:** Returns `False` when valueset data isn't loaded or resource is null. Per CQL three-valued logic, should return `NULL` (unknown). Returning `False` silently excludes patients from quality measure populations.
- **Fix:** Return `None` for null inputs and missing valueset data. Only return `False` when codes are definitively not found.
- **AC:** `in_valueset(NULL, ...)` returns NULL. Missing valueset returns NULL. Existing tests pass.

#### P0-4. `Implies` Macro Wrong Truth Table
- **Files:** `fhir4ds/fhirpath/duckdb/macros/logical.py:49,54` AND `fhir4ds/cql/duckdb/macros/logical.py:52-60`
- **Background:** `null implies null` returns `true` but spec says `null` (empty). Python UDF path is correct; SQL macro path diverges.
- **Fix:** Change `WHEN a IS NULL AND b IS NULL THEN NULL`.
- **AC:** `Implies(NULL, NULL)` returns NULL in both SQL macro and Python paths.

#### P0-5. C++ Out-of-Bounds Array Access in `days_in_month`
- **Files:** `extensions/fhirpath/src/fhirpath/evaluator.cpp:4430` AND `extensions/cql/src/cql/datetime.cpp:7-13`
- **Background:** `daysInMonth(y, m)` with `m=0` or `m>12` reads beyond static array bounds.
- **Fix:** Add `if (month < 1 || month > 12) return 30;` guard before array access.
- **AC:** `days_in_month(2024, 0)` and `days_in_month(2024, 13)` return safe defaults.

#### P0-6. Global Mutable Constants Singleton (Thread Safety)
- **File:** `fhir4ds/fhirpath/engine/invocations/constants.py:20-41`
- **Background:** Module-level `constants` singleton with mutable `today`, `now`, `timeOfDay`. Concurrent evaluations (DuckDB vectorized UDFs) wipe each other's cached values.
- **Fix:** Move constants into the `ctx` dict per evaluation.
- **AC:** Concurrent FHIRPath evaluations produce independent `now()` values.

#### P0-7. `FP_Quantity.deep_equal` Uses Result Before None-Check
- **File:** `fhir4ds/fhirpath/engine/nodes.py:316-324`
- **Background:** `conv_unit_to` can return `None` (incompatible units), but `.unit`/`.value` accessed before the check.
- **Fix:** Move `if converted is not None:` guard before `reverse_converted` call.
- **AC:** `deep_equal` with incompatible units returns `False`, not `AttributeError`.

#### P0-8. `to_time` Crashes on Empty Collection
- **File:** `fhir4ds/fhirpath/engine/invocations/misc.py:167-181`
- **Background:** `rtn[0]` raises `IndexError` when collection is empty.
- **Fix:** `return util.get_data(rtn[0]) if rtn else []`
- **AC:** `toTime({})` returns empty collection.

#### P0-9. Hardcoded Absolute Path in Fluent Function Loader
- **File:** `fhir4ds/cql/translator/fluent_function_loader.py:75`
- **Background:** `/mnt/d/duckdb-fhirpath/benchmarking/...` hardcoded. Fails on all other machines.
- **Fix:** Remove line 75 (duplicate of line 71 which uses relative path).
- **AC:** No absolute paths in source code. Fluent function loading works without `/mnt/d/`.

#### P0-10. DQM `except Exception` Swallows All Errors
- **File:** `fhir4ds/dqm/evaluator.py:371-372`
- **Background:** Catches ALL exceptions including `TypeError`, `MemoryError` as `DQMError`. Masks real bugs.
- **Fix:** Catch only `duckdb.Error`, `ValueError`, `RuntimeError`.
- **AC:** `TypeError` and `MemoryError` propagate. Expected errors wrapped as `DQMError`.

### P1: HIGH Architecture Violations (Fix Next)

#### P1-1. Pure AST Pipeline: Eliminate `SQLRaw` Mid-Pipeline
- **Files:** `cte_manager.py:63-88,550-564`, `_lists.py:1058-1062`, `_operators.py:189-201`, `_query.py:96-215`
- **Background:** ~15 sites call `to_sql()` mid-pipeline then wrap in `SQLRaw`. Downstream phases cannot inspect or transform these nodes.
- **Fix:** Build all SQL from AST nodes (`SQLFunctionCall`, `SQLBinaryOp`, `SQLSelect`).
- **AC:** Zero `SQLRaw` nodes in the AST pipeline. `grep -r "SQLRaw" translator/` returns only `types.py` definition.

#### P1-2. Singleton Semantics: Replace `LIMIT 1` with Cardinality Check
- **Files:** 13+ sites across `_core.py`, `_lists.py`, `fluent_functions.py`, `cte_manager.py`
- **Background:** CQL `singleton from` must return NULL for >1 element. `LIMIT 1` silently picks one.
- **Fix:** Use `CASE WHEN COUNT(*)=1 THEN value ELSE NULL END` pattern.
- **AC:** `singleton from` on multi-element collection returns NULL, not arbitrary first element.

#### P1-3. `SQLFunctionCall.to_sql()` Contains Business Logic
- **File:** `fhir4ds/cql/translator/types.py:312-394`
- **Background:** 82-line `to_sql()` contains `array_length` → `CASE WHEN`, `fhirpath_text(union)` → `COALESCE`, `intervalFromBounds` → `CAST`. These are semantic transforms in serialization.
- **Fix:** Extract into a pre-serialization normalization pass.
- **AC:** `to_sql()` is pure serialization with no conditional rewrites.

#### P1-4. FHIRPath `__eq__` Returns String Instead of Boolean
- **File:** `fhir4ds/fhirpath/engine/nodes.py:821-823, 932-934, 1023-1025`
- **Background:** `FP_Date.__eq__`, `FP_DateTime.__eq__`, `FP_Time.__eq__` return `getDateMatchStr()` (a string), not a boolean.
- **Fix:** `return self.getDateMatchStr() == other`
- **AC:** `FP_Date("2024") == "2024"` returns `True` (bool), not `"2024"` (str).

#### P1-5. Parser Imports from DuckDB Layer (Upward Dependency)
- **File:** `fhir4ds/fhirpath/parser/__init__.py:10`
- **Background:** `from ..duckdb.errors import FHIRPathSyntaxError` — core layer imports from UDF layer.
- **Fix:** Define `FHIRPathSyntaxError` in `fhir4ds/fhirpath/engine/errors.py`, import from there.
- **AC:** No imports from `duckdb` package in `fhirpath/parser/` or `fhirpath/engine/`.

#### P1-6. ViewDef JoinType Validation No-Op
- **File:** `fhir4ds/viewdef/parser.py:310`
- **Background:** Compares `JoinType` enum against raw strings. Never fires. Invalid join types pass silently.
- **Fix:** Compare against `JoinType` enum members.
- **AC:** `JoinType("invalid")` raises `ValueError`.

#### P1-7. ViewDef Hardcoded `_FHIR_ARRAY_ELEMENTS`
- **File:** `fhir4ds/viewdef/generator.py:343-367`
- **Background:** ~50 hardcoded element names for collection heuristic. Incomplete, unmaintainable.
- **Fix:** Use StructureDefinition metadata or spec `collection: true` flag.
- **AC:** New FHIR resources don't require code changes for array detection.

#### P1-8. DQM Performance Rate Unclamped
- **File:** `fhir4ds/dqm/evaluator.py:185-188`
- **Background:** Performance rate can be negative or >1. Clinically dangerous for quality reporting.
- **Fix:** Clamp `[0.0, 1.0]` + warn on out-of-range.
- **AC:** Performance rate always in [0,1]. Out-of-range logged as warning.

#### P1-9. DQM Silent Date Guess
- **File:** `fhir4ds/dqm/evaluator.py:263-264`
- **Background:** Uses Jan 1 – today when measurement period missing. Wrong period = wrong clinical report.
- **Fix:** Raise `DQMError("Measurement period required")`.
- **AC:** Missing measurement period raises clear error.

#### P1-10. C++ Parser Thread Safety
- **File:** `extensions/fhirpath/src/fhirpath/fhirpath_extension.cpp:84,148`
- **Background:** Shared `g_fhirpath_parser` singleton with mutable `tokens_`/`pos_` state.
- **Fix:** Create stack-local `Parser` per `parse()` call. Remove shared singleton.
- **AC:** Concurrent `parse()` calls produce correct results.

### P2: MEDIUM Structural Improvements (Next Sprint)

- **Break mega-functions:** `_translate_query` (1363 lines), `_translate_property` (605 lines), `_translate_identifier` (589 lines), `_wrap_definition_cte` (400+ lines)
- **Eliminate code duplication:** Definition-resolution (3x), parser workaround (7x), temporal methods (~80% shared)
- **Promote undeclared context attributes:** `_definition_cql_asts`, `_alias_resource_types`, `_needs_demographics` to proper `SQLTranslationContext` fields
- **Thread-safe caches:** Replace module-level mutable globals with per-context or locked caches
- **Remove deprecated UDF modules:** `cql/duckdb/udf/{math,string,logical,aggregate}.py` — macros cover all functionality
- **Fix `hasattr`/`getattr` duck-typing:** Use `isinstance()` with proper type checks
- **Consolidate duplicated helpers:** `_arrow_scalar_as_py` (3 copies), `_parse_datetime` (2 copies), `camel_to_snake` (2 copies), unit mappings (3 copies)

### P3: LOW Code Quality (Backlog)

- Remove dead code (13 instances)
- Fix typos in comments (6 instances)
- Add missing `@staticmethod` decorators
- Replace `type().__name__` with `isinstance()`
- Fix variable shadowing of builtins (`list`, `str`, `next`)
- Add type annotations to helper functions
- Pre-compute sorted/frozen lookup structures
- Document three-valued logic reliance on SQL semantics

---

## Positive Observations

The following components exemplify the target architecture:

1. **`status_filter_extractor.py`** — Excellent "CQL is Source of Truth" implementation. Extracts filters from CQL AST, no hardcoding.
2. **`terminology.py`** — Clean AST pipeline. All SQL via AST nodes. `KeyError` on missing definitions (Fail Fast).
3. **`model_config.py`** — Clean three-layer schema versioning. Exemplary design.
4. **`quantity.py` (patterns/)** — Proper UDF delegation via AST nodes.
5. **`interval.py` (patterns/)** — Correct `SQLInterval` AST node usage throughout.
6. **Three-tier macro/UDF model** — Well-designed layered approach in `cql/duckdb/`.
7. **C++ extensions** — Previous audit fixes (thread-safety, exception handling, regex caching) show good remediation process.

---

## Test Compliance Status

| Suite | Passed | Failed | Skip | Rate |
|-------|--------|--------|------|------|
| All Unit/Integration | 6,465 | 4 (pre-existing) | 64 | 99.94% |
| FHIRPath R4 Compliance | 934 | 1 | 0 | 99.9% |
| CQL Parse Compliance | 3,044 | 0 | 63 | 100% |
| SQL-on-FHIR v2 Spec | 140 | 0 | 0 | 100% |

Pre-existing failures (not caused by audit):
- `test_now`, `test_today`, `test_time_of_day` — timing-sensitive datetime tests
- `test_registration_fails_fast_without_pint` — pint dependency test
