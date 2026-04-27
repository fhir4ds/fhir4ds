# Phase 3 Architect Audit — Iteration 103

## Audit Scope
Focused review of 7 recently resolved issues (QA8-004, QA8-005, QA9-001/002/003/004, QA10-001).

## Conformance Verification

Verified from `conformance/reports/` JSON artifacts:

| Suite | Result | Status |
|-------|--------|--------|
| FHIRPath (R4) | 935/935 | ✅ 100% |
| CQL | 1706/1706 | ✅ 100% |
| ViewDefinition (v2) | 134/134 | ✅ 100% |
| DQM (QI Core) | 42/46 | ✅ 4 known upstream failures (CMS1017, CMS135, CMS145, CMS157) |

## Findings

### QA8-004 — in_valueset placeholder error message
- **File**: `fhir4ds/cql/duckdb/extension.py:144-155`
- **Assessment**: SOUND. The placeholder UDF raises `duckdb.InvalidInputException` with a clear,
  actionable message explaining how to load value sets. It only registers when the C++ extension
  fails to load (`if not cpp_loaded`), so it cannot mask a successful registration. The error
  message correctly references the public API (`register_valueset_udfs`). The function signature
  matches the real `in_valueset` UDF (3 args, `null_handling="special"`). No silent fallback —
  the error is raised at call time, not swallowed.

### QA8-005 — FHIR resource type validation in ViewDef parser
- **File**: `fhir4ds/viewdef/parser.py:267-318`
- **Assessment**: SOUND with one LOW observation (see ARC-103-001 below). The validation is
  non-blocking (warning only), which is correct — ViewDefinitions may legitimately reference
  custom resource types from IGs. The `_KNOWN_FHIR_RESOURCES` set is comprehensive (covers
  all R4B/R5 resource types). Uses `logging.warning()` consistent with the codebase's
  non-fatal diagnostic pattern.

### QA9-001 — warnings.warn for undefined CQL definitions
- **File**: `fhir4ds/cql/translator/expressions/_core.py:848-861`
- **Assessment**: SOUND. The dual-channel approach (both `logger.warning()` and `warnings.warn()`)
  ensures visibility in both log-consuming and interactive contexts. The guard
  `if _inlining_lib is None` correctly exempts definitions that are expected to resolve from
  an inlined library. Falls through to `SQLIdentifier` (existing behavior) — the warning is
  additive, not behavior-changing. `import warnings as _w` is inline to avoid module-level
  import overhead on the hot path; this is consistent with the codebase pattern.

### QA9-002 — warnings.warn for unknown CQL functions
- **File**: `fhir4ds/cql/translator/expressions/_functions.py:551-565`
- **Assessment**: SOUND. Mirrors QA9-001 structure exactly — same dual-channel pattern, same
  inlining guard, same import style. Consistent with the definition warning. Both warnings
  include the specific name and actionable guidance.

### QA9-003 — Date/time literal validation in CQL lexer
- **File**: `fhir4ds/cql/parser/lexer.py:1165-1209`
- **Assessment**: SOUND. Validates year (4-digit), month (1-12), day (1-31), hour (0-23),
  minute (0-59), second (0-59). Correctly strips timezone suffixes before time validation.
  Raises `LexerError` (the canonical error for this module) with line/column information.
  The validation is intentionally lenient on edge cases (e.g., Feb 30 is allowed at the lexer
  level — semantic validation belongs in a later pass), which is appropriate for a tokenizer.
  No new dependencies or cross-module coupling introduced.

### QA9-004 — Contained resource resolution in FHIRPath resolve()
- **File**: `fhir4ds/fhirpath/engine/invocations/navigation.py:60-69`
- **Assessment**: SOUND. Handles `#id` references by searching `root_data.contained[]`,
  matching on `resource_data.id == contained_id`. Correctly uses `util.get_data()` to unwrap
  ResourceNode wrappers. Returns the raw resource (not `resource_data`) which preserves
  ResourceNode identity for downstream FHIRPath evaluation. Returns `None` (not `[]`) on
  failure, consistent with the `_resolve_reference` return contract. The `root_data` used
  is the dataRoot, which correctly represents the current evaluation context's root resource.

### QA10-001 — Aggregate functions on list expressions
- **File**: `fhir4ds/cql/translator/expressions/_utils.py:32-59`
- **File**: `fhir4ds/cql/translator/expressions/__init__.py:168` (flatten in registry)
- **File**: `fhir4ds/cql/translator/translator.py:493-498` (CTE bare expression wrapping)
- **Assessment**: SOUND. `_is_list_returning_sql()` detects list-producing SQL patterns to
  prevent double-wrapping. The function list is comprehensive (includes `flatten`, `list_concat`,
  `list_distinct`, etc.) and handles nested `SQLSubquery`/`SQLSelect` recursion. The `flatten`
  registration in `_RENAMES` (line 168) follows the existing rename pattern. The CTE bare
  expression wrapping (`translator.py:493-498`) correctly wraps non-SELECT/non-Subquery
  expressions in `SQLSelect(columns=[expr])` and unwraps `SQLSubquery` to get the inner query.

## Low-Severity Observations

### ARC-103-001 — _KNOWN_FHIR_RESOURCES defined inline in function body
- **Severity**: LOW
- **File**: `fhir4ds/viewdef/parser.py:267-309`
- **Category**: Code organization
- **Description**: The `_KNOWN_FHIR_RESOURCES` set (~150 entries) is defined as a local variable
  inside the `parse_viewdefinition()` function. This means it is reconstructed on every call.
  Additionally, `import logging as _logging` on line 310 is redundant — `logging` is already
  imported at module level (line 10) and used as `_logger` (line 15).
- **Impact**: Negligible performance cost (set construction is fast). No correctness issue.
- **Proposed Fix**: Move `_KNOWN_FHIR_RESOURCES` to module level. Remove the redundant
  `import logging as _logging` and use the existing `_logger` instead of creating `_vd_logger`.

### ARC-103-002 — Lexer date validation allows month=0 when non-numeric
- **Severity**: LOW
- **File**: `fhir4ds/cql/parser/lexer.py:1180`
- **Category**: Defensive validation
- **Description**: The `isdigit()` guard before `int()` conversion means non-numeric month/day
  strings silently pass validation. This is fine for the lexer (regex already constrains format),
  but worth noting as a defensive gap if the upstream regex ever changes.
- **Impact**: None in practice — the token-scanning loop only feeds valid date characters here.
- **Proposed Fix**: No action required. Document the regex dependency.

## Verdict

All 7 fixes are architecturally sound:
- ✅ No new abstractions that bypass existing patterns
- ✅ No hardcoded values where configuration should be used
- ✅ No silent fallbacks — all error/warning paths surface actionable information
- ✅ No coupling violations — changes stay within their module boundaries
- ✅ Conformance suite passes at expected levels (935/935, 1706/1706, 134/134, 42/46)

**AUDIT: PASSED**
