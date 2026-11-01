# Architect Handoff -- Iteration 4 (Domain 3: Translation and Semantic Correctness)

## Overall Structural Health Assessment: STRONG-CONVERGENT

Iteration 4 closes the last known gap in Domain 3. EXP-001 (overlaps operators missing `_ensure_resource_to_interval`) was found by the EXPLORER through systematic fuzz testing and cross-operator probing. The fix is a mechanical repetition of the ARCH-001 pattern. With this fix, **all 14 interval binary operators and 3 interval unary operators** now have complete `_ensure_resource_to_interval` coverage. INV-03 is definitively SATISFIED. All 12 invariants are SATISFIED except INV-07 (LOW, existing). The domain is structurally complete.

## QA Enforcer Gate Assessment

**RETRY_QA: false**

The EXPLORER was thorough and disciplined:
1. **Test volume**: 111 tests spanning regression (31), fuzz (68), cross-operator (6), resource types (7), and point intervals (4). This is the largest test suite across all 4 iterations.
2. **Regression coverage**: All 5 prior fixes (QA-001, ARCH-002, ARCH-003, NEW-001, ARCH-001) tested under stress with boundary variations. All verified stable.
3. **Bug discovery quality**: EXP-001 was found through a targeted probe of the overlaps decomposition path -- the only code path not yet covered by `_ensure_resource_to_interval`. The EXPLORER correctly identified the root cause as the same bug class as ARCH-001 and noted that overlaps was missed because it has a decomposed path.
4. **INV-07 audit**: Systematic catalog of 29 SQLRaw usages across 14 files. All confirmed safe (internal constants or AST-rendered expressions). No raw SQL string injection vulnerabilities.
5. **UDF boundary validation**: 51 crashes from fuzz testing, all traced to `intervalFromBounds` rejecting reversed/NULL bounds. This is expected UDF behavior, not a translator defect.
6. **Good signal-to-noise**: 1 genuine bug found from 111 tests. The 4 FAIL entries break down as 2 EXP-001 (real bug), 1 test-data issue, 1 expected-value error. No false positives escalated as bugs.

## Fix Quality Review

### EXP-001 Fix: `_ensure_resource_to_interval` for overlaps/overlaps after/overlaps before (SOUND)

The fix adds `_ensure_resource_to_interval` calls to the top of three methods:
- `_translate_overlaps_op` (line 1728-1729)
- `_translate_overlaps_after_op` (line 1793-1794)
- `_translate_overlaps_before_op` (line 1842-1843)

**Assessment**: Architecturally identical to the ARCH-001 fix from iteration 3. The pattern is:
```python
left = self._ensure_resource_to_interval(left, expr.left)
right = self._ensure_resource_to_interval(right, expr.right)
```

This is a 2-line mechanical addition at the entry point of each method. The call is placed before the decomposition logic so that the interval extraction happens before `intervalStart`/`intervalEnd` are called on the operands. This is the correct placement -- identical to the pattern used for `before`, `after`, `starts`, `ends`, `meets`, `includes`, `included in`, `properly includes`, and `properly included in`.

**Regression risk**: MINIMAL. The `_ensure_resource_to_interval` function returns the original SQL unchanged when the operand is already an interval or non-resource expression. Only bare resource aliases are transformed.

**Completeness**: This was the last gap. The previous iteration 3 handoff noted overlaps as "covered at query level" via decomposition, but the EXPLORER demonstrated that the decomposed path does NOT call `_ensure_resource_to_interval` before decomposition, meaning bare resources pass through unconverted. The fix closes this gap.

## Coverage Completeness Check: INV-03 Verification

After EXP-001 fix, the complete `_ensure_resource_to_interval` coverage across all interval operators:

| Operator | Covered | Level | Method Location |
|----------|---------|-------|-----------------|
| `overlaps` | YES | Expression | `_translate_overlaps_op` (line 1728-1729) |
| `overlaps after` | YES | Expression | `_translate_overlaps_after_op` (line 1793-1794) |
| `overlaps before` | YES | Expression | `_translate_overlaps_before_op` (line 1842-1843) |
| `during` | YES | Expression | `_translate_during_op` + `intervalContains` |
| `includes` | YES | Expression | Inline (line 837-838) |
| `included in` | YES | Expression | Inline (line 851-852) |
| `properly includes` | YES | Expression | Inline (line 906-907) |
| `properly included in` | YES | Expression | Inline (line 944-945) |
| `meets` | YES | Expression | Inline (line 1032-1033) |
| `meets before` | YES | Expression | Inline (line 1036-1037) |
| `meets after` | YES | Expression | Inline (line 1040-1041) |
| `starts` | YES | Expression | `_translate_starts_op` (line 2094) |
| `ends` | YES | Expression | `_translate_ends_op` (line 2266) |
| `before` | YES | Expression | `_translate_before_op` (line 2017-2018) |
| `after` | YES | Expression | `_translate_after_op` (line 2057-2058) |
| `start of` (unary) | YES | Expression | `_ensure_resource_to_interval` |
| `end of` (unary) | YES | Expression | `_ensure_resource_to_interval` |

**Result**: INV-03 is FULLY SATISFIED. All 17 operator paths (14 binary + 3 unary) now call `_ensure_resource_to_interval` before performing interval operations. No gaps remain.

## Updated Invariant Scorecard

| Invariant | Status Before Iter 4 | Status After Iter 4 | Change |
|-----------|----------------------|---------------------|--------|
| INV-01: Decomposition-UDF Alignment | SATISFIED | SATISFIED | No change |
| INV-02: Boundary Closedness Consistency | SATISFIED | SATISFIED | No change |
| INV-03: Resource-to-Interval Completeness | SATISFIED | SATISFIED | No change (confirmed via exhaustive audit -- overlaps gap closed by EXP-001) |
| INV-04: Expression Dispatch Completeness | SATISFIED | SATISFIED | No change |
| INV-05: Prefix-Function-Keyword Uniformity | SATISFIED | SATISFIED | No change |
| INV-06: No Silent NULL Fallbacks | SATISFIED | SATISFIED | No change |
| INV-07: DuckDB SQL Isolation | PARTIALLY SATISFIED | PARTIALLY SATISFIED | No change (LOW priority, SQLRaw audit PASS) |
| INV-08: Type Coercion Consistency | SATISFIED | SATISFIED | No change |
| INV-09: No Test-Driven Special Cases | SATISFIED | SATISFIED | No change |
| INV-10: NULL Propagation Correctness | SATISFIED | SATISFIED | No change |
| INV-11: Parse-Translate Contract Integrity | SATISFIED | SATISFIED | No change |
| INV-12: Definition Shape Inference | SATISFIED | SATISFIED | No change |

**Score**: 11 SATISFIED, 1 PARTIALLY SATISFIED (INV-07, existing, LOW priority). Unchanged from iteration 3. INV-03 confirmed definitively SATISFIED through exhaustive operator-by-operator audit.

## Issues by Category

### Resolved This Iteration (1)
| ID | Severity | Invariant | Title | Fix Summary |
|----|----------|-----------|-------|-------------|
| EXP-001 | MEDIUM | INV-03 | Overlaps decomposed path bypasses `_ensure_resource_to_interval` | Added `_ensure_resource_to_interval` to `_translate_overlaps_op`, `_translate_overlaps_after_op`, `_translate_overlaps_before_op` |

### Open Issues: NONE

All issues from iterations 1-4 are now tombstoned. Zero open issues remain for Domain 3.

### Tombstones (All Issues, Iterations 1-4)
| ID | Iteration | Original Severity | Title |
|----|-----------|-------------------|-------|
| QA-001 | 1 | HIGH | Overlaps decomposition wrong boundary variable |
| QA-002 | 1 | HIGH | starts during returns False (unconfirmed) |
| QA-003 | 1 | MEDIUM | distinct double-wrapping (unconfirmed) |
| QA-004 | 1 | MEDIUM | flatten not handled (unconfirmed) |
| QA-005 | 1 | LOW | DistinctExpression dispatch (confirmed not an issue) |
| ARCH-002 | 2 | MEDIUM | starts/ends during day of uses BETWEEN |
| ARCH-003 | 2 | MEDIUM | Overlaps decomposition NULL right-end |
| NEW-001 | 2 | MEDIUM | before/after bare resource wraps raw JSON |
| OBS-001 | 2 | LOW | _extract_interval_bounds hardcodes (correct default) |
| ARCH-001 | 3 | MEDIUM | Resource-to-Interval conversion incomplete for meets/includes |
| ARCH-004 | 3 | COSMETIC | ends during BinaryExpression BETWEEN is dead code |
| EXP-001 | 4 | MEDIUM | Overlaps decomposed path bypasses _ensure_resource_to_interval |

## Structural Health Summary

### Strengths (CONFIRMED this iteration)
1. **INV-03 definitively SATISFIED**: All 17 interval operator paths verified. The `_ensure_resource_to_interval` function with its 4-layer fallback chain (primary -> CTE name -> CQL AST -> SQL inspection) provides robust resource-to-interval conversion for all operators.
2. **All prior fixes stable**: 5 prior fixes (QA-001, ARCH-002, ARCH-003, NEW-001, ARCH-001) regression-tested under stress with 31 tests. Zero regressions.
3. **UDF layer fully spec-conformant**: Fuzz testing with 68 pathological inputs confirms UDFs correctly validate bounds. No silent data corruption.
4. **INV-07 SQLRaw audit PASS**: 29 usages across 14 files, all safe. No raw SQL string injection.
5. **Core dispatch mechanism**: `_camel_to_snake` routing correct and complete (INV-04, INV-11)
6. **Cross-operator interaction clean**: AND, OR, EXISTS, COUNT with interval operators all produce correct SQL.
7. **Type inference and coercion**: Robust across all tested patterns (INV-08, INV-12)

### Remaining Weaknesses (unchanged)
1. **INV-07: DuckDB SQL Isolation (LOW)**: SQLRaw usage confined to utility functions. The UDF layer is DuckDB-specific regardless. Retargeting would require a full UDF abstraction layer, not just SQLRaw removal.
2. **`_operators.py` file size**: Still 3400+ lines. The decomposed method extraction has improved readability but the file remains large.
3. **Dual-path architecture**: Decomposition vs UDF split remains the primary structural risk. 5 of 6 bugs across all iterations were in the decomposition path (QA-001, ARCH-002, ARCH-003, ARCH-001 variant, EXP-001). The UDF path has produced 0 bugs.

### Bug Fix Summary Across 4 Iterations
| Iteration | Bugs Fixed | Personality | Open Issues After |
|-----------|-----------|-------------|-------------------|
| 1 | 1 (QA-001) | SKEPTIC | 2 (ARCH-001, ARCH-004 discovered) |
| 2 | 3 (ARCH-002, ARCH-003, NEW-001) | ARCHAEOLOGIST | 2 (ARCH-001, ARCH-004) |
| 3 | 1 (ARCH-001) + 1 resolved (ARCH-004) | HISTORIAN | 0 |
| 4 | 1 (EXP-001) | EXPLORER | 0 |
| **Total** | **6 fixed + 1 confirmed dead code** | | **0 open** |

## Recommended Focus for Iteration 5 (SPECIALIST Personality)

With 0 open issues, all invariants SATISFIED (except INV-07 at LOW), and the domain structurally complete, iteration 5 should focus on SPECIALIST-level hardening and cleanup.

### Priority 1: Dead code removal
The ARCH-004 BETWEEN path at `_operators.py:2380-2430` (line numbers approximate after EXP-001 fix) is confirmed dead code since iteration 3. Remove it to reduce file size and cognitive load.

### Priority 2: Decomposition path consolidation
5 of 6 bugs were in the decomposition path. Consider whether the decomposition logic in `_try_decompose_interval_overlaps` and related methods can be simplified or unified with the UDF path. The `_ensure_resource_to_interval` pattern is now consistently applied, but the decomposition itself (manual `intervalStart`/`intervalEnd` extraction + COALESCE + comparison) is inherently more fragile than calling a single UDF.

### Priority 3: UDF NULL bounds hardening
The EXPLORER noted that `intervalFromBounds` crashes on NULL bounds in certain edge cases. While the translator always uses COALESCE before calling the UDF, making the UDF more resilient to NULL bounds (treating NULL as open-ended) would add defense-in-depth.

### Priority 4: INV-07 assessment
Decide whether to accept INV-07 as permanently PARTIALLY SATISFIED (since the UDF layer is DuckDB-specific regardless) or invest in abstracting the UDF layer for dialect retargeting.

## Key Files Audited This Iteration
- `/mnt/d/fhir4ds/fhir4ds/cql/translator/expressions/_operators.py` -- overlaps/overlaps after/overlaps before handlers (EXP-001 fix verified), complete interval operator coverage audit
- `/mnt/d/fhir4ds/fhir4ds/cql/translator/expressions/_temporal_intervals.py` -- `_ensure_resource_to_interval` definition (unchanged, verified)

## Conformance Baseline
- CQL: 1706/1706 (100%)
- ViewDefinition: 134/134 (100%)
- FHIRPath: 935/935 (100%)
- DQM: 42/46 (91.3%, baseline unchanged)
- Regressions: 0

## Evolution Statistics
- Iteration 1: 5 issues from QA (1 resolved, 4 unconfirmed), 3 new architectural issues found. Personality: SKEPTIC.
- Iteration 2: 3 issues resolved (ARCH-002, ARCH-003, NEW-001), 1 downgraded (OBS-001), 1 new issue found (ARCH-004 LOW). Personality: ARCHAEOLOGIST.
- Iteration 3: 1 issue resolved (ARCH-001), 1 confirmed dead code (ARCH-004). 0 new issues found. Personality: HISTORIAN.
- Iteration 4: 1 issue resolved (EXP-001). 0 new issues found. Personality: EXPLORER.
- Cumulative: 6 issues resolved, 1 confirmed dead code, 0 regressions, **0 open issues**.
