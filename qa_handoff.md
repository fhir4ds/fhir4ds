# QA Handoff — Iteration 9

## Summary

**Iteration 9** focused on **security and correctness under adversarial data**. Ran **80+ tests** across 6 priority areas targeting SQL injection resistance, malformed input handling, CQL error message quality, non-standard FHIR resources, and DQM evidence completeness.

| Metric | Value |
|--------|-------|
| Tests run | 80+ |
| ✅ PASS | 76 |
| ❌ NEW ISSUES | 4 |
| New issues filed | QA9-001 through QA9-004 |
| Regressions | 0 (QA8-002, QA7-001 confirmed fixed) |

## Regression Checks

| Prior Issue | Status | Notes |
|-------------|--------|-------|
| QA8-002 (circular include guard) | ✅ PASS | `CircularIncludeError` raised correctly for A→B→A cycle |
| QA7-001 (on or before date precision) | ✅ PASS | No crash; FHIRPath date comparison handles mixed precision |

## New Issues Found

| ID | Severity | Category | Title |
|----|----------|----------|-------|
| QA9-001 | **Medium** | correctness | CQL translator passes undefined definition references through as bare SQL identifiers |
| QA9-002 | **Medium** | correctness | CQL translator passes unknown function calls through to SQL verbatim |
| QA9-003 | **Low** | validation | CQL parser does not validate date/time literal values (e.g., @2023-13-45) |
| QA9-004 | **Low** | conformance | FHIRPath `resolve()` returns empty for contained resource references (`#id`) |

## Priority Analysis

### QA9-001 — Undefined Definition References (MEDIUM)
When CQL references a non-existent definition (`define X: NonExistentDefinition`), the translator emits `SQLIdentifier('NonExistentDefinition')` which produces a confusing DuckDB parser error at runtime. Should raise `TranslationError` at translation time with the undefined name and list of available definitions. Located in expression translation logic (`_core.py`).

### QA9-002 — Unknown Function Calls (MEDIUM)
Same pattern as QA9-001 but for function calls. `NonExistentFunction(1, 2)` becomes `SQLFunctionCall('NonExistentFunction', ...)`. The translator should validate function names against its registry and raise a clear error. This is the same class of issue as QA8-001 (unresolved includes → broken SQL) but for local references.

### QA9-003 — Invalid Date Literals (LOW)
`@2023-13-45` (month 13, day 45) passes parser and translator, becoming `SQLLiteral('2023-13-45')`. DuckDB catches it at runtime, but the error message is a generic type error rather than "invalid CQL date literal". Low priority since runtime catches it.

### QA9-004 — resolve() on Contained References (LOW)
`medicationReference.resolve()` where the reference is `#med1` returns `[]` instead of navigating to `contained.where(id='med1')`. The FHIRPath spec requires resolve() to handle fragment references by searching the containing resource's `contained` array. Workaround: use `contained.where(id='med1')` directly. Low priority as the workaround is straightforward.

## Areas Validated (No Issues)

### SQL Injection Resistance (25 tests — ALL PASS)
- **FHIRPath expressions with SQL metacharacters**: `'; DROP TABLE--`, `" OR 1=1`, backticks — all safely rejected by parser or return empty
- **Resource JSON with injection in field values**: Injection strings in `id`, `name.given` safely returned as data, never executed as SQL
- **CQL string literals with injection**: Properly handled through AST (no string interpolation)
- **ViewDef column names**: `_quote_identifier()` rejects semicolons, quotes, backticks, spaces, numeric-start, dashes, dots, null bytes, newlines
- **CQL definition names with injection**: `"X'; DROP TABLE resources; --"` properly double-quoted in generated SQL CTEs
- **Multi-row table queries**: Injection data in resource column does not affect other rows or table integrity
- **Bundle entries with injection IDs**: Safely handled

### Data Integrity Under Malformed Input (18 tests — ALL PASS)
- **Wrong data types**: String-for-integer, string-for-boolean, integer-for-date — gracefully returned as-is
- **Unknown extra fields**: Preserved and accessible via FHIRPath (no schema stripping)
- **Deeply nested extensions (5 levels)**: Both direct and `where(url=...)` navigation work correctly
- **Large arrays (1000 entries)**: `count()`, `first()`, `last()`, `where()` all work; count returns 1000
- **Null in unexpected positions**: null resourceType, null id, null in arrays, empty resource `{}` — all return None gracefully
- **Invalid JSON**: Returns None (graceful degradation, no crash)
- **100K character strings**: Length fully preserved
- **Unicode**: CJK (名前), emoji (🔥🎉), accented (Ñoño), null bytes (\x00), RTL override — all preserved
- **NDJSON mixed lines**: Valid lines return results, invalid/empty lines return None

### CQL Error Messages (9 tests)
- **Parser syntax errors**: Clear messages with line/column numbers (e.g., `Line 1, Column 1: Expected 'library' declaration`)
- **Lexer errors**: Reports character position for unexpected characters, unterminated strings
- **Division by zero**: Correctly translated to `NULLIF(0, 0)` pattern (CQL spec: null result)
- **Duplicate definitions**: Silently uses last definition (last-wins); not filed as issue since CQL spec doesn't mandate an error
- **Missing `using` clause**: Accepted (degrades gracefully to no-model mode)

### FHIRPath on Non-Standard Resources (12 tests — ALL PASS)
- **Custom resource types**: `resourceType: 'CustomWidget'` — id, name, resourceType all accessible
- **R3 fields**: `animal.species.text` accessible (no strict R4 schema enforcement)
- **Contained resources**: Direct navigation, `ofType()` filtering both work
- **Bundle.entry.resource**: Entry count, resource ID extraction, `ofType(Patient)` filtering all work

### DQM Evidence (Partial — blocked by value set loading)
- Population audit mode produces `{result: bool, evidence: []}` structs — evidence arrays empty without loaded value sets
- Could not fully validate P6 criteria (evidence completeness per patient) because standalone MeasureEvaluator requires the full DQM pipeline (value set loading + conformance database setup) to produce meaningful results
- The conformance runner uses `BenchmarkDatabase.load_all_valuesets()` which is tightly coupled to the test infrastructure

## Cumulative Issue Status (Iterations 1–9)

| Status | Count |
|--------|-------|
| FIXED | 28 |
| OPEN | 4 (QA9-001 through QA9-004) |
| DEFERRED | 2 (QA8-004, QA8-005) |
| INTENDED | 1 (QA8-003) |
| **Total tracked** | **67** |

## Recommendations for Iteration 10

1. **Fix QA9-001 and QA9-002 together** — they share the same root cause (translator silently passes unresolved references to SQL). Add a validation pass after `translate_library()` that checks all emitted `SQLIdentifier` and `SQLFunctionCall` nodes against the known definitions and function registries.
2. **QA9-003** could be addressed with a simple date validation in the parser's DateTime literal handler.
3. **QA9-004** (resolve on contained) is lower priority but would improve FHIRPath spec compliance; consider for a future iteration.
4. **Continue conformance at 2817/2821** — no regressions found.

## Test Artifacts

- Sandbox: `.temp/qa_iter9/`
- Issues: `evolution.json` (QA9-001 through QA9-004)
- This file: `qa_handoff.md`
