# QA Handoff — Iteration 5

## Summary
Iteration 5 performed a **specification deep dive** across FHIRPath §5 (Type System), CQL §18-22 (Intervals, Date/Time), and SQL-on-FHIR v2 (ViewDefinition). After 120+ targeted tests, **4 new issues** were identified and **no regressions** were found.

Key discovery: the Python fallback FHIRPath evaluator has 3 spec compliance gaps that the C++ extension handles correctly. The most impactful finding is a CQL translator bug that silently produces wrong results for precision-qualified temporal comparisons.

## Regression Smoke (Priority 1) — ✅ ALL PASS
Tested 5 representative resolved issues: QA-003, QA-008, QA3-001, QA4-003, QA4-004. All confirmed stable.

## New Issues

| ID | Severity | Component | Title |
|----|----------|-----------|-------|
| QA5-001 | MEDIUM | FHIRPath (Py) | Inequality w/ incompatible types throws error instead of empty (§5.3) |
| QA5-002 | MEDIUM | FHIRPath (Py) | Cannot parse dateTime literals `@YYYY-MM-DDTHH:MM:SS` (§2.3) |
| QA5-003 | LOW | FHIRPath (Py) | String literal as first token before `&` operator causes parse error |
| QA5-004 | HIGH | CQL Translator | `same or before [prec] of` emits string equality instead of temporal UDF |

### QA5-001: Inequality Error Instead of Empty (Python Evaluator Only)
**Spec:** FHIRPath §5.3 — "If the operand types are not the same, the result is empty ({})."
**Repro:** `FHIRPathEvaluator: '1 < true'` → `FHIRPathError` (Python) vs `[]` (C++ ✅)
**Scope:** Python fallback only. C++ extension returns `[]` correctly.
**Fix:** In InequalityExpression handler, catch type mismatch → return `[]`.

### QA5-002: DateTime Literal Parsing (Python Evaluator Only)
**Spec:** FHIRPath §2.3 — dateTime literals `@YYYY-MM-DDTHH:MM:SS` are valid.
**Repro:** `FHIRPathEvaluator: '@2020-01-01T10:00:00'` → `FHIRPathSyntaxError`
**Scope:** ALL dateTime literals with time component fail. Date-only and time-only work. C++ extension passes all conformance tests for dateTime literals.
**Fix:** Fix dateTime regex/tokenizer in the Python parser.

### QA5-003: String Literal + & Parse Error (Python Evaluator Only)
**Spec:** FHIRPath §6.3 — `'a' & 'b'` is valid string concatenation.
**Repro:** `FHIRPathEvaluator: "'a' & 'b'"` → `FHIRPathSyntaxError`
**Workaround:** `('a') & ('b')` works. Path-first expressions like `Patient.id & '-test'` work.
**Fix:** Fix parser tokenizer for `&` after string literal.

### QA5-004: CQL `same or before [precision] of` Mistranslation ⚠️ HIGHEST PRIORITY
**Spec:** CQL §19.15-16 — `same or before month of` should do precision-aware temporal comparison.
**Repro:**
```
translate_cql("define T: @2020-06 same or before month of @2020-07")
→ SQL: '2020-06' = '2020-07'  (WRONG: string equality, returns FALSE)
Expected: cqlSameOrBeforeP('2020-06', '2020-07', 'month')  (returns TRUE)
```
**Root Cause:** Parser correctly produces operator `"same or before month of"`. But `_translate_same_operator()` in `_temporal_comparisons.py` only handles `"same month or before"` (precision-first form), not the precision-last form. The operator falls through to a generic fallback that emits string equality.
**Affected:** `same or before [prec] of`, `same or after [prec] of` — both forms.
**Not Affected:** `before [prec] of`, `after [prec] of`, `same [prec] or before` — all correct.
**Scope:** Always active — CQL translator is pure Python, not affected by extension choice.
**Fix:** Add patterns for `f"same or before {precision} of"` and `f"same or after {precision} of"` in `_translate_same_operator()` that extract precision and call `cqlSameOrBeforeP`/`cqlSameOrAfterP`.

## Areas Confirmed Clean

| Area | Tests | Verdict |
|------|-------|---------|
| FHIRPath §5.1 Existence (empty/exists/allTrue/anyTrue/allFalse/anyFalse) | 10 | ✅ All pass |
| FHIRPath §5.2 Equality (decimal=int, case sensitivity, ~ equivalence, empty) | 10 | ✅ All pass |
| FHIRPath §5.3 Comparison (string, date, empty propagation) | 4 | ✅ (C++ path) |
| FHIRPath §5.4 Collections (union, combine, distinct, first/last/tail/skip/take, where, select, repeat, indexer) | 16 | ✅ All pass |
| FHIRPath §5.6 Math (div, mod, division, overflow, abs, ceiling, floor, round, ln, sqrt, power, empty propagation) | 16 | ✅ All pass |
| FHIRPath §5.7 String (replace, split, indexOf, substring, startsWith/endsWith, contains, matches, length, toChars, upper/lower, replaceMatches, trim) | 15 | ✅ All pass |
| FHIRPath §5.8 Tree Navigation (children, descendants, children < descendants) | 3 | ✅ All pass |
| FHIRPath §5.9 Type Functions (is, as, ofType — via Python evaluator) | 6 | ✅ (with correct type names) |
| FHIRPath §5.10 Boolean Logic (and/or/xor/implies, three-valued with empty) | 11 | ✅ All pass |
| FHIRPath Conversion Functions (toString, toInteger, toDecimal, toBoolean, convertsToX) | 6 | ✅ All pass |
| CQL §18 Interval Ops (overlaps, union, intersect, includes, in, start/end, width, Size, properly includes, overlaps before/after, meets before/after, expand, collapse) | 20 | ✅ All pass |
| CQL §22 Date/Time (same-precision compare, different-precision → null, before/after, date arithmetic, months/days between, leap year) | 10 | ✅ All pass |
| ViewDef (duplicate columns, nested forEach×2, complex paths, forEachOrNull LEFT JOIN, where, constants, collection, unionAll, deep nesting, validation, execution) | 13 | ✅ All pass |

## Conformance Baseline
Unchanged at **2817/2821**.

## Note on Python vs C++ FHIRPath Evaluators
Three of four new issues (QA5-001, QA5-002, QA5-003) affect only the **Python fallback evaluator**, which is used when the C++ extension cannot be loaded (unsigned development builds, unsupported platforms). The C++ extension — used in production and conformance testing — handles all these cases correctly. These are still real issues since:
1. The Python evaluator is a public API (`FHIRPathEvaluator`)
2. Development builds default to the Python path (unsigned C++ extensions require explicit opt-in)
3. The Python path should maintain spec parity with the C++ extension

## Recommendation
- **Fix QA5-004 immediately** — silently wrong results for standard CQL syntax, always active
- **Fix QA5-001** — one-line fix (catch + return empty), improves spec compliance
- **Defer QA5-002 and QA5-003** — C++ path is correct; Python parser fixes are more involved
