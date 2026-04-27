# Architect Handoff — Iteration 9 (ARCHITECT → QA)

**Verdict**: PASSED
**Phase**: ARCHITECT → QA (iteration 9)
**Conformance**: 2817/2821 (99.9%) — matches baseline

## Iteration 8 Fix Review

Two fixes from QA8/FIX8 were reviewed against all 12 architecture invariants:

| Fix | Severity | Files Changed | Invariants Checked | Verdict |
|-----|----------|---------------|--------------------|---------|
| QA8-002 Circular include detection | HIGH | `errors.py`, `translator.py`, `include_handler.py` | INV-01,02,03,04,09,12 | ✅ CLEAN |
| QA8-001 Unresolved include fail-fast | MEDIUM | `context.py`, `_property.py`, `_core.py`, `include_handler.py` | INV-01,02,03,04,09,12 | ✅ CLEAN |

**All fixes comply.** No new SQLRaw mid-pipeline, no to_sql() mid-pipeline, no silent fallbacks introduced. Both fixes are pure error-detection paths that raise before any SQL generation occurs.

### QA8-002: Circular include detection (HIGH)
- `CircularIncludeError` added as subclass of `TranslationError` in `fhir4ds/cql/errors.py` — proper error hierarchy (INV-09: layer separation).
- `_resolving_stack` is a frozenset of `(path, version)` tuples threaded through child translator instances via `__init__` parameter. No mutation of shared state.
- Cycle detection occurs in `include_handler.py:183` *before* recursive load — fail-fast (INV-04).
- Diamond dependencies unaffected: cache handles dedup, stack only tracks the *current* resolution path.
- No SQL types (`SQLRaw`, `SQLExpression`, etc.) involved — purely AST/control-flow logic (INV-01/02).

### QA8-001: Unresolved include fail-fast (MEDIUM)
- `_unresolved_includes` set added to `SQLTranslationContext` — pure bookkeeping, no SQL generation.
- Two guard sites added: `_property.py:406` and `_core.py:862`. Both check `context.is_include_unresolved()` and raise `TranslationError` immediately — no partial SQL emitted (INV-04).
- Error messages include actionable guidance (library name, missing loader hint).
- Include is still registered in `context.includes` for introspection — doesn't break test harnesses that inspect includes without executing SQL.

### QA8-003/004/005: INTENDED/DEFERRED
No code changes — architectural assessment only. Reviewed and concur with dispositions.

## Conformance (verified — no regression)

```
ViewDefinition:    134/134   (100.0%)
FHIRPath (R4):     935/935   (100.0%)
CQL:               1706/1706 (100.0%)
DQM (QI Core):     42/46     (91.3%)
─────────────────────────────────────
OVERALL:           2817/2821 (99.9%) — AT BASELINE
```

## CQL Unit Tests

```
3329 passed, 1 failed (ARCH-004 pre-existing), 55 skipped, 2 xpassed, 135 warnings
```

The single failure (`test_bp_profile_includes_component_columns`) is pre-existing
(ARCH-004) — confirmed across multiple iterations.

QA8-specific tests: 7/7 passed (`test_include_errors.py`).

## 12 Invariants — All Holding

| Invariant | Description | Status |
|-----------|-------------|--------|
| INV-01 | No SQLRaw mid-pipeline | ✅ No new violations |
| INV-02 | No to_sql() mid-pipeline | ✅ No new violations |
| INV-03 | No silent fallbacks | ✅ No new violations |
| INV-04 | Fail fast on errors | ✅ Both fixes are fail-fast |
| INV-05 | Hardcoded resources externalized | ✅ Not affected |
| INV-06 | No new Strategy 2 templates | ✅ Not affected |
| INV-07–08 | Type safety / parameter binding | ✅ Not affected |
| INV-09 | Layer separation | ✅ Error classes in errors.py, detection in translator layer |
| INV-10–11 | CTE naming / dedup | ✅ Not affected |
| INV-12 | Test coverage for fixes | ✅ 7 new tests |

INV-06 (Strategy 2 templates) remains KNOWN_DEBT — no change.

## Open ARCH Issues (unchanged)

| ID | Severity | Summary |
|----|----------|---------|
| ARCH-001 | MEDIUM | Strategy 2 body_sql templates (KNOWN_DEBT, blocked Task C4) |
| ARCH-002 | MEDIUM | Profile registry silent fallback |
| ARCH-004 | MEDIUM | Stale unit test (test_bp_profile_includes_component_columns) |
| ARCH-009 | MEDIUM | UDF broad exception catches |
| ARCH-005 | LOW | Broad exception in fhirpath_is_valid |
| ARCH-006 | LOW | ViewDef module-level array load |
| ARCH-007 | LOW | ViewDef string-based SQL generation |
| ARCH-008 | LOW | Context profile registry warning fallback |

No new ARCH issues introduced. No CRITICAL or HIGH open findings.

## Cumulative Progress (28 RESOLVED across 8 iterations)

| Iteration | Issues Found | Fixed | Deferred/Intended | Net New |
|-----------|-------------|-------|-------------------|---------|
| 1 | 30 | 5 | 12 | 13 open |
| 2 | 0 | 3 | 0 | 10 open |
| 3 | 0 | 3 | 7 | 0 new |
| 4 | 4 | 4 | 0 | 0 new |
| 5 | 2 | 2 | 0 | 0 new |
| 6 | 1 | 0 | 1 | 0 new |
| 7 | 3 | 3 | 0 | 0 new |
| 8 | 5 | 2 | 3 | 0 new |

## Convergence Assessment

The evolution loop is converging strongly:
- Iterations 4–8 found only MEDIUM/LOW issues (the HIGH in iter 8 was a latent recursion bug, not a regression).
- All fixes are clean against invariants. No cascading breakage.
- Conformance holds steady at 2817/2821 across all 8 iterations.
- The codebase is stable. QA9 should confirm exit readiness.

## Next Phase

QA iteration 9. If QA9 finds no new CRITICAL/HIGH findings, the loop should exit.
