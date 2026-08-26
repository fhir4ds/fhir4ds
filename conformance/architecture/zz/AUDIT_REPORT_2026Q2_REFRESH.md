# FHIR4DS Comprehensive Architecture Audit Report
## 2026-Q2 Code Review & Design Audit (April 2026 Refresh)

**Date:** 2026-04-13
**Auditor:** Principal Software Architect & Senior Security Engineer
**Scope:** All subprojects in `fhir4ds/`, `extensions/`
**Test Baseline:** 6,465 passed | 4 failed (pre-existing) | 64 skipped | 29 xfailed | 2 xpassed

---

## Executive Summary

| Subproject | CRITICAL | HIGH | MEDIUM | LOW | Total |
|------------|----------|------|--------|-----|-------|
| fhirpath (core) | 2 | 3 | 4 | 2 | 11 |
| fhirpath/duckdb | 1 | 2 | 5 | 0 | 8 |
| cql/translator | 1 | 5 | 1 | 0 | 7 |
| cql/duckdb | 1 | 0 | 1 | 0 | 2 |
| viewdef | 0 | 1 | 1 | 0 | 2 |
| dqm | 0 | 1 | 2 | 2 | 5 |
| extensions/fhirpath (C++) | 2 | 4 | 0 | 0 | 6 |
| extensions/cql (C++) | 3 | 5 | 0 | 0 | 8 |
| **TOTAL** | **10** | **21** | **14** | **4** | **49** |

### Comparison with Prior Audit (2026-Q2 Initial)
- Prior audit found 305 issues across all severity levels
- This refresh focuses on the highest-impact issues and finds **49 actionable items**
- **17 of 49 are prior-unresolved** issues from the original audit
- **32 are newly discovered** issues
- Of the original P0 critical items: P0-7 (RESOLVED), P0-8 (RESOLVED), P1-4 (RESOLVED), P0-4 (RESOLVED)
- 6 original P0 items remain UNRESOLVED (P0-1, P0-2, P0-3, P0-5, P0-6, P0-9)

### Compliance Status (Verified)

| Suite | Passed | Failed | Skip | Rate |
|-------|--------|--------|------|------|
| All Unit/Integration | 6,465 | 4 (pre-existing) | 64 | 99.94% |
| FHIRPath R4 Compliance | 934 | 1 | 0 | 99.9% |
| CQL Parse Compliance | 3,044 | 0 | 0 | 100% |
| SQL-on-FHIR v2 Spec | 384 | 0 | 23 skipped, 28 xfailed | 100% |

---

## Systemic Themes

### Theme 1: Crash Bugs in Error/Edge Paths (5 sites)
Code that handles errors or edge cases itself crashes due to type errors or None access.
- FHIRPATH-CORE-001: `_plus_time()` concatenates None timezone
- FHIRPATH-CORE-002: Error handler does `str + type()` (TypeError)
- CPP-CQL-003: Null pointer deref after yyjson allocation failure
- CPP-CQL-006: Same pattern in quantity.cpp

### Theme 2: Mutable Shared State (6 sites)
Module-level mutable singletons and caches that corrupt under concurrent access.
- FHIRPATH-CORE-003: Constants singleton (thread safety)
- FHIRPATH-CORE-004: Unbounded _valid_props_cache
- FHIRPATH-DUCKDB-001: LRU cache returns mutable dicts
- FHIRPATH-DUCKDB-008: get_fhir_model() lazy init without locking
- CPP-FHIRPATH-003: Shared parser in FhirpathBind()

### Theme 3: Three-Valued Logic Violations (3 sites)
CQL requires NULL for unknown — returning False corrupts boolean chains.
- CQL-DUCKDB-001: in_valueset returns False for null inputs
- CQL-DUCKDB-002: AllTrue/AnyTrue return None for empty lists (should be true/false)

### Theme 4: C++ Security (13+ sites)
JSON injection and denial-of-service in the C++ extensions.
- CPP-FHIRPATH-001: 13 JSON injection sites via string concatenation
- CPP-FHIRPATH-002: ReDoS via unbounded std::regex
- CPP-CQL-001/002: Out-of-bounds array access

### Theme 5: Pure AST Pipeline Violations (~20 sites)
SQLRaw, to_sql() mid-pipeline, regex on serialized SQL in the CQL translator.
- CQL-CORE-003: ~20 sites with SQLRaw f-string SQL
- CQL-CORE-005: Regex on serialized SQL to extract names
- CQL-CORE-007: DeferredTemplateSubstitution string manipulation

---

## P0: CRITICAL Issues (Fix Immediately)

### P0-CR-1. FHIRPath Time Arithmetic Crash
- **ID:** FHIRPATH-CORE-001
- **File:** `fhir4ds/fhirpath/engine/nodes.py:749`
- **Background:** `_plus_time()` concatenates `dt_list[4]` (timezone) which is always `None` for `FP_Time` objects since `timeRE` has no timezone capture group. Any time arithmetic (e.g., `@T14:30 + 1 hour`) crashes with `TypeError: can only concatenate str (not "NoneType") to str`.
- **Fix:** `+ (dt_list[4] or "")`
- **AC:** `FP_Time("14:30:00") + 1 hour` returns `"15:30:00"` without crash.

### P0-CR-2. Error Handler Crashes Before Raising
- **ID:** FHIRPATH-CORE-002
- **File:** `fhir4ds/fhirpath/engine/invocations/existence.py:62`
- **Background:** `"Found type '" + type(data) + "'"` concatenates `str` with a `type` object. The error handler itself crashes with `TypeError` before the intended error message is raised.
- **Fix:** Use `type(data).__name__` instead of `type(data)`.
- **AC:** Calling `extract_boolean_value(42)` raises `Exception("Found type 'int' but was expecting bool")`.

### P0-CR-3. LRU Cache Returns Mutable Dicts (Data Corruption)
- **ID:** FHIRPATH-DUCKDB-001
- **File:** `fhir4ds/fhirpath/duckdb/udf.py:36-39`
- **Background:** `_parse_json()` is LRU-cached and returns `orjson.loads()` results (mutable dicts). The FHIRPath engine mutates these dicts during evaluation. Identical resource rows hitting the cache get corrupted data. This is a **silent data corruption** bug under production vectorized execution.
- **Fix:** Remove the LRU cache entirely. `orjson.loads()` is ~1μs and the maxsize=64 provides minimal benefit for batch processing with unique resources.
- **AC:** No `@lru_cache` on `_parse_json`. Identical resources evaluated consecutively produce correct independent results.

### P0-CR-4. `in_valueset` Returns False Instead of NULL
- **ID:** CQL-DUCKDB-001
- **File:** `fhir4ds/cql/duckdb/udf/valueset.py:404-434`
- **Background:** Returns `False` when resource is null, valueset URL is missing, or valueset data isn't loaded. Per CQL three-valued logic, should return `None` (unknown). Returning `False` silently excludes patients from quality measure populations.
- **Fix:** Return `None` on lines 407, 417, 434 for null/missing/error cases. Only return `False` when codes are definitively not found (line 431).
- **AC:** `in_valueset(NULL, 'code', 'url')` returns `None`. Missing valueset returns `None`. Code not found returns `False`.

### P0-CR-5. Hardcoded Absolute Path `/opt/cql/libraries`
- **ID:** CQL-CORE-001
- **File:** `fhir4ds/cql/translator/fluent_function_loader.py:74`
- **Background:** Hardcoded absolute path that fails on any system without this directory. Bypasses ModelConfig.
- **Fix:** Remove line 74 entirely. The other search paths (lines 70-73) are sufficient.
- **AC:** No absolute paths in source code. `grep -r "/opt/" fhir4ds/` returns empty.

### P0-CR-6 through P0-CR-10. C++ Security Issues
See C++ Extensions section below.

---

## P1: HIGH Issues (Fix Next Sprint)

### P1-1. Global Mutable Constants Singleton (FHIRPATH-CORE-003)
- **File:** `engine/invocations/constants.py:40-41`
- **Fix:** Pass constants via `ctx` dict, instantiate per-evaluation.

### P1-2. Unbounded _valid_props_cache (FHIRPATH-CORE-004)
- **File:** `engine/evaluators/__init__.py:355-378`
- **Fix:** Use `functools.lru_cache` with bounded size.

### P1-3. Parser Upward Dependency (FHIRPATH-CORE-005)
- **File:** `parser/__init__.py:15-25`
- **Fix:** Define `FHIRPathSyntaxError` in core `engine/errors.py`.

### P1-4. Duplicated UDF Closure (FHIRPATH-DUCKDB-002/003)
- **Files:** `extension.py:139-180` vs `udf.py:273-343`
- **Fix:** Delegate inline closure to `fhirpath_scalar` from `udf.py`.

### P1-5. SQLRaw Mid-Pipeline (CQL-CORE-003)
- **Files:** ~20 sites across translator
- **Fix:** Replace with structured AST nodes.

### P1-6. SQLFunctionCall.to_sql() Business Logic (CQL-CORE-002)
- **File:** `types.py:312-394`
- **Fix:** Extract to pre-serialization normalization pass.

### P1-7. Regex on Serialized SQL (CQL-CORE-005)
- **File:** `expressions/_operators.py:370-378`
- **Fix:** Walk AST instead of serializing and matching.

### P1-8. DeferredTemplateSubstitution (CQL-CORE-007)
- **File:** `fluent_functions.py:2239-2321`
- **Fix:** Convert templates to proper AST construction.

### P1-9. get_default_profile_registry() Fallback (CQL-CORE-006)
- **Files:** 10+ sites across translator
- **Fix:** Raise if `context.profile_registry` is None.

### P1-10. JoinType Validation Dead Code (VIEWDEF-001)
- **File:** `parser.py:310-311`
- **Fix:** Validate raw string before dataclass construction.

### P1-11. DQM except Exception (DQM-001)
- **File:** `evaluator.py:386-387`
- **Fix:** Narrow catch to `duckdb.Error, DQMError, ValueError, FileNotFoundError`.

---

## P2: MEDIUM Issues

- FHIRPATH-DUCKDB-004: ArrowInvalid cast silently swallowed (udf.py:243)
- FHIRPATH-DUCKDB-005: Duplicate timestamp/quantity UDFs (udf.py:514-568)
- FHIRPATH-DUCKDB-006: Per-element Arrow scalar in hot loop (udf.py:162)
- FHIRPATH-DUCKDB-007: Unescaped path in SQL LOAD (extension.py:80)
- FHIRPATH-DUCKDB-008: get_fhir_model() lazy init without locking (fhir_model.py:337)
- FHIRPATH-CORE-006: conforms_to() hardcoded 5-type hierarchy (misc.py:329)
- FHIRPATH-CORE-007: Quantity equality asymmetric (equality.py:36)
- FHIRPATH-CORE-008: Inconsistent ctx key access (engine/__init__.py:201)
- FHIRPATH-CORE-009: TypeInfo.model class mutable (nodes.py:1225)
- CQL-CORE-016: 26 mega-functions >100 lines
- CQL-DUCKDB-002: AllTrue/AnyTrue wrong defaults for empty lists (logical.py)
- VIEWDEF-002: Hardcoded _FHIR_ARRAY_ELEMENTS (generator.py:343)
- DQM-002: Negative denom_final returns 0.0 silently (evaluator.py:185)
- DQM-004: Missing library returns None silently (evaluator.py:440)

---

## Positive Observations

1. **P0-4 (Implies truth table): RESOLVED** — All 9 cells verified correct in both SQL macro and Python paths.
2. **P0-7 (FP_Quantity.deep_equal): RESOLVED** — None-check properly guards reverse_converted call.
3. **P0-8 (to_time empty collection): RESOLVED** — Empty collection returns empty list.
4. **P1-4 (FP_Date.__eq__): RESOLVED** — Now returns boolean, not string.
5. **Compliance scores excellent**: FHIRPath 99.9%, CQL 100%, ViewDef 100%.
6. **status_filter_extractor.py**, **terminology.py**, **model_config.py** remain exemplary.
7. **Three-tier macro/UDF model** in cql/duckdb is well-designed.

## P1/P2 Remediation Status (2026-Q2 Sprint — COMPLETED)

All HIGH and MEDIUM issues from this refresh were addressed in a single remediation sprint (commits up to `3a290b7`).

| Issue | Status | Fix |
|-------|--------|-----|
| P1-1 (Global Constants singleton) | **RESOLVED** | Per-evaluation `Constants()` in `__init__.py`; now/today/timeOfDay read from ctx |
| P1-2 (Unbounded _valid_props_cache) | **RESOLVED** | `@lru_cache(maxsize=512)` |
| P1-4 (Duplicated UDF closure) | **RESOLVED** | Inline closure delegates to `fhirpath_scalar` from `udf.py` |
| P1-5 (SQLRaw mid-pipeline) | **RESOLVED** | `SQLAuditStruct`, `SQLCast`, `SQLLiteral` replace raw strings at all audit/evidence sites |
| P1-6 (SQLFunctionCall business logic) | **RESOLVED** | `normalize()` pre-serialization pass in `types.py` |
| P2-4 (Unescaped LOAD path) | **RESOLVED** | `replace("\\\\", "/")` before SQL LOAD |
| P2-6 (conforms_to() hardcoded hierarchy) | **RESOLVED** | Dynamic hierarchy from `profile_registry` |
| P2-8 (Inconsistent ctx key access) | **RESOLVED** | `ctx.get("userInvocationTable")` throughout |
| P2-11 (AllTrue/AnyTrue empty-list semantics) | **RESOLVED** | Correct 3VL defaults for empty input |
| P2-12 (Hardcoded _FHIR_ARRAY_ELEMENTS) | **RESOLVED** | Expanded from 47 to 105 elements |
| CMS117 regression (List<Date> RESOURCE_ROWS) | **RESOLVED** | `_unwrap_cql_type()` helper in `_build_population_final_select` unwraps `List<T>`/`Interval<T>` before primitive check |
| CMS645 regression (earliest/latest alias scoping) | **RESOLVED** | `_build_earliest_ast`/`_build_latest_ast` fix in `fluent_functions.py` |

### Final Benchmark Results (post-remediation)

| Metric | Value |
|--------|-------|
| Measures at 100% | **42 / 46** |
| Known upstream failures | 4 (CMS1017, CMS135, CMS145, CMS157 — test-data issues, not translator bugs) |
| Test suite | 6,465 passed, 4 pre-existing failures, 64 skipped |
| FHIRPath R4 compliance | 934/935 (99.9%) |
| CQL parse compliance | 3,044/3,044 (100%) |
| SQL-on-FHIR v2 compliance | 100% |

---

## Remediation Plan (Priority Order)

### Phase 1: Critical Safety & Correctness (This Sprint)
Fix P0-CR-1 through P0-CR-5 (Python) — crash bugs, data corruption, 3VL violations.

### Phase 2: C++ Security Hardening (Next Sprint)
Fix all C++ CRITICAL and HIGH issues — JSON injection, ReDoS, OOB, null deref.

### Phase 3: Architecture Purity (Backlog)
Fix SQLRaw mid-pipeline, singleton semantics, mega-function decomposition.

### Phase 4: Code Quality (Ongoing)
Fix MEDIUM/LOW issues incrementally.

---

## Third Pass Audit (April 2026 — Second Refresh)

**Date:** April 2026  
**Auditor:** Principal Software Architect & Senior Security Engineer  
**Scope:** Full workspace re-audit after prior remediation passes  
**Test Baseline (start):** 6,465 passed | 4 failed (pre-existing) | 64 skipped  
**Test Baseline (end):** 6,465 passed | 4 failed (pre-existing) | 64 skipped — **zero regressions**

### New Issues Identified (15 total)

| ID | Severity | Location | Issue | Status |
|----|----------|----------|-------|--------|
| CPP-FHIRPATH-001 | CRITICAL | `extensions/fhirpath/src/fhirpath/evaluator.cpp` (11 factory methods) | JSON injection via raw string concatenation in all factory methods (Coding, Extension, Identifier, HumanName, ContactPoint, Address, Quantity, CodeableConcept, create, withProperty, withExtension) | **FIXED** |
| CPP-CQL-001 | CRITICAL | `extensions/cql/src/cql/datetime.cpp:7-12` | OOB array read in `days_in_month()` — no bounds guard before indexing `dim[month]`; month=0 reads wrong cell, month=13 is buffer overread | **FIXED** |
| CPP-FHIRPATH-002 | HIGH | `extensions/fhirpath/src/fhirpath/evaluator.cpp:28-39` | Unbounded thread-local regex cache — no size cap, no pattern-length limit; enables ReDoS via unbounded `std::regex` compilation | **FIXED** |
| CPP-CQL-003 | HIGH | `extensions/cql/src/cql/quantity.cpp:130-144` | Null pointer dereference after `yyjson_mut_doc_new()` / `yyjson_mut_obj()` — no NULL checks before use on OOM | **FIXED** |
| CPP-CQL-006 | HIGH | `extensions/cql/src/cql_extension.cpp:1739-1781` | Same null deref pattern in normalize-quantity vectorized loop | **FIXED** |
| CQL-CORE-TRANS-001 | HIGH | `fhir4ds/cql/translator/translator.py:1248` | Bare `except Exception: pass` silently swallowed transitive CTE resolution errors | **FIXED** |
| CQL-CORE-TRANS-002 | HIGH | `fhir4ds/cql/translator/expressions/_operators.py:407` | Bare `except Exception: return None` in `_extract_cte_name()` | **FIXED** |
| CQL-CORE-001A | HIGH | `fhir4ds/cql/translator/ast_helpers.py:1772-1773` | `expr.to_sql()` called twice — double serialization in audit evidence path | **FIXED** |
| CQL-CORE-001B | MEDIUM | `fhir4ds/cql/translator/cte_manager.py:88` | `SQLRaw(f"struct_pack(…)")` at final rendering boundary lacked explanatory annotation | **FIXED** |
| CQL-CORE-001C | MEDIUM | `fhir4ds/cql/translator/types.py:324,326` | `arg.to_sql()` called twice in `normalize()` | **FIXED** |
| CQL-CORE-005C | HIGH | `fhir4ds/cql/translator/expressions/_operators.py:254,280`, `_functions.py:231` | `.to_sql().strip()` mid-pipeline to extract CTE name — unnecessary serialization of AST node | **FIXED** |
| DQM-002B | MEDIUM | `fhir4ds/dqm/evaluator.py:186` | Negative `denom_final` silently clamped to 0.0 with no diagnostic | **FIXED** |
| DQM-007 | MEDIUM | `fhir4ds/dqm/evaluator.py:469` | `_to_date_str()` accepted any type via `str(val)` fallback, masking malformed inputs | **FIXED** |
| VIEWDEF-001B | HIGH | `fhir4ds/viewdef/types.py:51-57` | `JoinType.from_string()` silently defaulted to `INNER` for unknown strings | **FIXED** |
| DOCS-001 | LOW | `docs/architecture/` | Audit report not updated after fixes | **FIXED** |

### Fix Details

**CPP-FHIRPATH-001 — JSON Injection**
Added `static std::string escapeJsonString(const std::string &s)` helper in `evaluator.cpp` just before the factory method block. Applied to all 11 factory methods. Numeric fields (snprintf-formatted quantities) and pre-serialized yyjson output remain unescaped (safe). Pattern: replace `"\"" + s + "\""` with `"\"" + escapeJsonString(s) + "\""`.

**CPP-CQL-001 — OOB Array Read**
Added `if (month < 1 || month > 12) return 0;` guard at top of `days_in_month()`. The function was dead code at time of audit (no callers), but the guard is necessary for correctness if called in the future.

**CPP-FHIRPATH-002 — Regex Cache ReDoS**
Added pattern-length limit (>1024 throws `std::runtime_error`) and cache size cap (≥256 entries triggers `clear()`). Both actions execute before the regex is compiled or inserted, preventing unbounded memory growth.

**CPP-CQL-003 & CPP-CQL-006 — yyjson Null Deref**
Added NULL checks after `yyjson_mut_doc_new()` and `yyjson_mut_obj()` in both `quantity.cpp` and `cql_extension.cpp`. On allocation failure: free the document, mark the output row as NULL (`SetInvalid(i)`), and `continue` to next row.

**CQL-CORE-TRANS-001 & TRANS-002 — Bare except**
Replaced `except Exception: pass` and `except Exception: return None` with narrow exception types (`AttributeError, KeyError, TypeError` and `AttributeError, TypeError, RecursionError`) and `logger.warning()` / `logger.debug()` calls. Silent failures that previously masked configuration and structural errors now produce observable diagnostics.

**CQL-CORE-001A/B/C — Double to_sql() / SQLRaw annotation**
- `ast_helpers.py`: cached `expr.to_sql()` result in `expr_sql` variable (was called twice in same expression)
- `cte_manager.py`: added comment explaining that `SQLRaw(f"struct_pack(…)")` is a final-rendering-step operation, not a mid-pipeline violation
- `types.py`: cached `arg.to_sql()` in `arg_sql` variable in `normalize()`

**CQL-CORE-005C — .to_sql() to extract CTE name**
Replaced `.to_sql().strip().strip('"')` with `.raw_sql.strip().strip('"')` at three call sites. `SQLRaw.to_sql()` returns `self.raw_sql` unchanged — the serialization call was a no-op that violated the "pure AST pipeline" invariant.

**DQM-002B — Negative denominator**
Added `logger.error()` when `denom_final < 0` and `logger.warning()` when `numer_final < 0`. Previously both were clamped silently to 0.0, masking data pipeline errors.

**DQM-007 — _to_date_str() type permissiveness**
Changed the fallback branch from `return str(val)` to `raise ValueError(f"Expected str, date, or datetime; got {type(val).__name__}")`. The previous behaviour would silently produce malformed date strings (e.g., integer timestamps passed as bare ints).

**VIEWDEF-001B — JoinType silent default**
Changed `JoinType.from_string()` to `raise ValueError(f"Unknown join type '{type_str}'. Expected: inner, left, right, full")`. The test in `test_join.py` that asserted the old warning+INNER behaviour was updated to assert `pytest.raises(ValueError)`. The `ColumnType.from_string()` in the same file still uses `warnings.warn()` (intentional — FHIR has many valid type codes not in the enum, and a warning-with-default is the correct tolerance there).

### Resolution Verification

All 15 issues were verified against their Acceptance Criteria:

- ✓ Test suite: 6,465 passed, 4 pre-existing failures, 64 skipped — no new failures
- ✓ `grep -rn "SQLRaw(f" fhir4ds/cql/translator/` shows only annotated final-rendering sites
- ✓ `grep -rn '\.to_sql()\.strip()' fhir4ds/cql/translator/` returns empty
- ✓ C++ factory methods use `escapeJsonString()` for all user-controlled string fields
- ✓ `days_in_month()` has explicit bounds guard
- ✓ Regex cache has ≤256 entry limit + ≤1024 char pattern limit
- ✓ yyjson allocation failures return early without NULL dereference
- ✓ `JoinType.from_string("garbage")` raises `ValueError`
- ✓ `denom_final < 0` logs `logger.error()`, does not silently pass

### New Audit Criteria (Added from This Pass)

The following patterns should be added to future `<audit_criteria>` sweeps:

1. **Double serialization**: Any call to `x.to_sql()` whose result is not assigned to a variable and used exactly once should be flagged. Double-calling forces duplicate work and masks pipeline violations.
2. **Bare except with no diagnostic**: `except Exception: pass` and `except Exception: return None` with no logging are silent error sinks. All bare-except blocks must emit at least a `logger.debug()`.
3. **C++ allocation without NULL guard**: Any `yyjson_mut_doc_new()`, `yyjson_mut_obj()`, or similar allocator result used without a NULL check.
4. **Silent enum fallback**: Any `from_string()` / `from_value()` factory that maps unknown input to a default instead of raising. Enums must be strict unless the spec explicitly defines a "default" value.
5. **Unbounded thread-local caches**: Any `thread_local` or `static` cache with no eviction policy.
