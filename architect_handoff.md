# Architect Handoff — Iteration 8 (ARCHITECT → QA)

**Verdict**: PASSED
**Phase**: ARCHITECT → QA (iteration 8)
**Conformance**: 2817/2821 (99.9%) — matches baseline

## Iteration 7 Fix Review

Three fixes from QA7/FIX7 were reviewed against all 12 architecture invariants:

| Fix | Severity | File | Invariants Checked | Verdict |
|-----|----------|------|--------------------|---------|
| QA7-001 Precision-of promotion | MEDIUM | `_operators.py:654-664` | INV-01,02,03,04,12 | ✅ CLEAN |
| QA7-002 List aggregate unwrap | MEDIUM | `_functions.py:127-136,714` | INV-01,02,03,04,12 | ✅ CLEAN |
| QA7-003 None guard in parse() | LOW | `dqm/parser.py:43-44` | INV-04 | ✅ CLEAN |

**All fixes comply.** No SQLRaw mid-pipeline, no to_sql() mid-pipeline, no silent fallbacks introduced.

### QA7-001: Precision-of promotion (`_operators.py`)
Detects `BinaryExpression(operator="precision of")` nested in the right operand of
`on or before`/`on or after`, extracts precision, and promotes it into the operator
string. Pure CQL AST transformation — no SQL layer involvement.

### QA7-002: List aggregate unwrap (`_functions.py`)
Extends `_unwrap_list_source()` to recognize `flatten` (FunctionRef) and
`union`/`except`/`intersect` (BinaryExpression). Aggregate handler now checks
`_is_list_returning_sql()` alongside `isinstance(SQLArray)`.

### QA7-003: None guard (`dqm/parser.py`)
Raises `MeasureParseError` on None input instead of leaking `AttributeError`.

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
3384 passed, 1 failed (ARCH-004 pre-existing), 2 xpassed, 135 warnings
```

The single failure (`test_bp_profile_includes_component_columns`) is pre-existing
(ARCH-004) — confirmed by running against parent commit.

## 12 Invariants — All Holding

All 3 fixes verified against applicable invariants. No violations introduced.
INV-11 (no new Strategy 2 templates) remains KNOWN_DEBT — no change.

## Pre-existing Architectural Note

The explore agent flagged a pre-existing `to_sql()` + `SQLRaw` mid-pipeline usage
in `_operators.py:708-714` (DateTime cast validation). This is **not** part of the
QA7 fixes — it predates this iteration. Tracked for future remediation but not a
blocker.

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

## Cumulative Progress (26 RESOLVED across 7 iterations)

| Iteration | Issues Found | Fixed | Deferred | Net |
|-----------|-------------|-------|----------|-----|
| 1 | 30 | 5 | 12 | 13 open |
| 2 | 0 | 3 | 0 | 10 open |
| 3 | 0 | 3 | 7 | 0 new |
| 4 | 4 | 4 | 0 | 0 new |
| 5 | 2 | 2 | 0 | 0 new |
| 6 | 1 | 0 | 1 | 0 new |
| 7 | 3 | 3 | 0 | 0 new |

## Next Phase

QA iteration 8. The loop has been converging steadily — iteration 7 found only
MEDIUM/LOW issues, all resolved. If QA8 finds no new CRITICAL/HIGH findings,
the loop should exit.
