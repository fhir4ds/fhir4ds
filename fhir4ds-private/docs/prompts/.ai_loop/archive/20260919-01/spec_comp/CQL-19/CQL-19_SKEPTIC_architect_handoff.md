# Architect Handoff — CQL-19 launch (SKEPTIC), iteration 1

## Structural audit summary
Audited the five fixes against the Golden Standard
(.temp/architect/golden_standard_cql19.md). Verdict: structurally sound.
- All fixes are translator-level, type-directed rewrites (no SQLRaw, no
  silent fallbacks, no test-specific special cases). Native layer untouched;
  binaries md5-matched repo == site-packages (cql 3e7d4167143e01907fdd8561db43b7d7,
  fhirpath 57d0634b6ee6eddee9fc06a1355bef5a).
- Promotion centralization is honored: no new per-operator ad-hoc scalar
  lowerings were introduced; the family-level args[0] promotion in
  _translate_function_ref mirrors the established _promote pattern.
- Stored-list routing reuses the single stores_list_value discriminator.

## Architectural findings (logged, not fixed — no RETRY_QA)
- ARCH-1 (debt, reaffirmed from CQL-18): the scalar-vs-multi-valued property
  distinction is still not statically modeled; every new list consumer must
  remember to promote. A multiplicity-aware property typing layer remains
  the structural fix. Recurrence count: 3 launches.
- ARCH-2 (debt): `_is_single_list_expr` vs `_is_list_returning_sql` are
  overlapping predicates; this launch needed a local widening wrapper
  (_properly_is_list) because the properly-includes dispatch used the
  narrower one. Consolidation recommended.
- ARCH-3 (watch): the union jsonConcat fallback can still silently wrap a
  list operand as a single element for operand shapes neither Case 6a/6b/6c
  recognize (mixed identifier+list unions). Case 6c covers the tested
  shapes; a typed error would be safer than jsonConcat nesting.

## QA quality gate
QA (SKEPTIC) performed hypothesis-first, spec-verified probing (normative
text fetched live; official fixtures cross-checked; three candidate findings
correctly adjudicated INTENDED via fixtures/3VL-lifted contexts). Dynamic,
alias, chained, and 3VL surfaces all covered. Engineer's recovery gate
caught a real DQM regression and root-caused it via a stash-based causality
test. RETRY_QA: false.

## Empirical validation (final tree, fresh run)
- Master gate: OVERALL 2832/2832 — ViewDefinition 144/144, FHIRPath 935/935,
  CQL 1706/1706 (CqlListOperatorsTest 212/212), DQM 47/47. Baseline holds.
- Focused: test_list_part2_parity.py 29/29 (16 new end-to-end dynamic-operand
  regression tests across py/cpp/no-python), test_list_part1_parity.py 9/9,
  test_v2_expressions.py 147/147.
- Logs: .temp/qa/cql19_skeptic/{gate_final.log,dqm3.log,probe1_final.out,probe2_final.out}

## State
All five issues VERIFIED and archived to ARCHIVE_LOG.md (tombstones in
evolution.json). Clean exit at min_iterations=1: zero non-terminal
CRITICAL/HIGH/MEDIUM issues. exit_reason CLEAN; workflow null; control
returns to the outer spec-compliance orchestrator.

## Recommended fix order (future launches)
1. ARCH-1 multiplicity-aware property typing layer (highest leverage).
2. ARCH-2 predicate consolidation (_is_single_list_expr ⊆ _is_list_returning_sql).
3. ARCH-3 replace the union jsonConcat fallback with typed errors for
   unrecognized list-context operand shapes.
