# CQL-19 EXPLORER — Architect Handoff (iteration 1, closeout audit)

## Scope
Audit of the two landed HIGH fixes (QA-001 alias-define stored-list marking +
element-rows union conversion; QA-002 `_list_operator_full_list_source`
materialization) and the QA-003 INTENDED adjudication. Translator-only; no
native/binaries touched.

## Golden-standard invariants checked
1. List-operator lowering must accept ANY list-valued operand (CQL 1.5 App B:
   Tail/Skip/Take/Length/SingletonFrom) — rows-shaped leaks into scalar/list
   context are spec violations, not cosmetic.
2. Physical-shape metadata (`stores_list_value`, `RowShape`, `has_resource`)
   must be conservative: marking a rows-shaped define as a stored list breaks
   DQM resource unions (CMS117/CMS645/CMS130/133 precedent).
3. No silent fallbacks: materialization paths must return None to existing
   paths rather than substituting defaults.
4. Gate fixtures outrank spec prose (established doctrine: union-null,
   ProperInNullRightFalse) — documented, in-code adjudications only.

## Findings — PASS, no new issues
- **QA-001 fix** (`translator.py:1809-1833`, `_operators.py:4200-4248`):
  alias-define propagation only fires when the target meta already carries
  `stores_list_value`, and forces `PATIENT_SCALAR` + `List<` cql_type —
  consistent with the existing stored-list physical shape. The element-rows
  union conversion is guarded on `peer_rows` (peer NOT rows-shaped), which
  preserves DQM resource-union rows semantics; the guard is explicit,
  commented, and regression-tested. No measure-ID or resource-type
  hardcoding; no layering violations.
- **QA-002 fix** (`_lists.py:2265-2385`, dispatch in `_functions.py`):
  `_list_operator_full_list_source` returns `Optional[SQLExpression]` and
  falls through to legacy paths on None — no silent substitution. The
  `_patient_list` correlation uses `resource_alias or patient_alias or "_pt"`
  matching the established correlation idiom; query-return wrapping reuses
  `_wrap_list_aggregate` rather than duplicating SQL construction.
  First/Last intentionally keep their window paths (documented). Predicate
  `_list_operator_source_is_retrieve_shaped` mirrors the materializer's
  branches — slight duplication of conditions, acceptable at LOW nuisance
  level; not logged as an issue.
- **QA-003 INTENDED**: rows-subquery singleton branch keeps `ELSE NULL` with
  an in-code adjudication comment at `_lists.py:2484-2494`; the typed §20.30
  error remains on element-exact paths and is pinned by an existing
  raises-test. Consistent with the fixtures-outrank-prose doctrine.

## QA quality gate (Phase 3)
EXPLORER QA was thorough: 3-engine parity probes, boundary counts, dedup
equivalence classes, alias chains, population-SQL reproducers, DQM
sensitivity flagged proactively. No QA veto; RETRY_QA not set.

## Empirical verification (final tree, this session)
- test_list_part2_parity.py: 47/47 (fresh).
- Focused list sweep (part1 parity + CQL unit): see orchestrator report.
- Master conformance gate: see orchestrator report (must be 2832/2832).

## State hygiene
Issues QA-001/QA-002 RESOLVED, QA-003 INTENDED — all terminal at iteration 1
(>= min_iterations 1). Clean exit; details retained in evolution.json +
qa/engineer handoffs (single-iteration run, no pruning to ARCHIVE_LOG needed).

## Recommended Fix Order
None — no open findings.
