# Architect Handoff — CQL-19 HISTORIAN launch, iteration 1

## Structural audit summary
Audited the four fixes against the CQL-19 Golden Standard
(.temp/architect/golden_standard_cql19.md). Verdict: structurally sound.
- All fixes are translator-level, type-directed rewrites: no SQLRaw, no
  silent fallbacks, no test-specific special cases. Native layer untouched;
  binaries md5-matched repo == site-packages (cql 3e7d4167143e01907fdd8561db43b7d7,
  fhirpath 57d0634b6ee6eddee9fc06a1355bef5a).
- QA-001 reuses the existing patient-correlated COUNT subquery pattern and
  resolves resource-define aliases through definition metadata (data-driven).
- QA-002 extracts `_apply_singleton_from_list_value` (dedup with the list
  branch) and reuses the established pre-hook + stored-list discriminator
  pattern from First/Last.
- QA-003's define-level allowlist widening is safe by construction (null
  literals and `as`-casts can never be resource CTEs; Identifier/Retrieve
  operands remain excluded, preserving the DQM resource-union guard).
- QA-004 unifies the error contract with the existing `[Resource].field` guard.

## Architectural findings (logged, not fixed — no RETRY_QA)
- ARCH-1 recurrence (4th launch): the scalar-vs-multi-valued property
  distinction is still not statically modeled; this launch's QA-002/QA-003
  are further instances of shape-recognition gaps (`_is_list_returning_sql`
  doesn't recognize stored-list value-column subqueries or all-null CASEs;
  the define-level union marking is an AST-shape allowlist). Multiplicity-
  aware property typing remains the highest-leverage structural fix.
- ARCH-4 (new, watch): `_is_static_null_case` previously rejected CASE-with-
  no-ELSE (which evaluates NULL) — predicate "statically null" correctness
  matters wherever null-as-empty short-circuits; now fixed, but sibling
  predicates (`_is_typed_list_expr`, `_is_list_returning_sql`) have the same
  "recognize every lowering of null/typed list" fragility (ties into ARCH-2
  consolidation from the SKEPTIC launch).

## QA quality gate
HISTORIAN QA performed memory-guided probing: fresh re-verification of all 5
SKEPTIC fixes (102 probe cases, zero diverge), DQM-sensitive retrieve-union
and aggregate-consumer surfaces per the launch mandate, plus 49 new cases on
axes the SKEPTIC pass could not cover by construction (aggregate-over-union,
stored-list singleton cardinality, union-null nesting over dynamic operands,
navigation-over-union error surface). One observation correctly adjudicated
INTENDED (nondeterministic union row order). RETRY_QA: false.

## Empirical validation (final tree, fresh run)
- Master gate: OVERALL 2832/2832 — ViewDefinition 144/144, FHIRPath 935/935,
  CQL 1706/1706, DQM 47/47 (final tree state, single pass, no retry needed).
- Focused: test_list_part2_parity.py 33/33 (5 new HISTORIAN regression tests),
  test_list_part1_parity.py 18/18, test_v2_expressions.py 147/147.
- Logs: .temp/qa/cql19_historian/{gate_final.log,probe_hist_final.out,
  probe_fix2.out}; SKEPTIC re-verify .temp/qa/cql19_skeptic/hist_reverify{1,2}_final.out.

## State
QA-001..QA-004 RESOLVED; QA-005 INTENDED. Archived to ARCHIVE_LOG.md with
tombstones in evolution.json. Clean exit at min_iterations=1: zero
non-terminal CRITICAL/HIGH/MEDIUM issues. exit_reason CLEAN; workflow null;
control returns to the outer spec-compliance orchestrator.

## Recommended fix order (future launches)
1. ARCH-1 multiplicity-aware property typing layer (highest leverage).
2. ARCH-2 predicate consolidation (_is_single_list_expr / _is_list_returning_sql
   / _is_typed_list_expr / _is_static_null_case share "recognize every
   lowering of X" responsibility).
3. ARCH-3 (SKEPTIC) typed errors for unrecognized list-context union operands.
