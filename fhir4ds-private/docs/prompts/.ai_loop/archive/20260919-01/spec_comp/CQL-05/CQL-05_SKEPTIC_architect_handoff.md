# Architect Handoff — CQL-05 Structural Type Operators (iteration 1)

## Golden Standard (invariants audited against)
1. Model knowledge data-driven (no inline clinical/resource maps in generic logic).
2. No SQLRaw / string SQL in mid-pipeline translation.
3. Dual-engine parity: translator-level fixes must hold for native C++ and forced-Python paths.
4. Translator layering respected (parsing / semantic AST / SQL generation / execution).
5. No silent fallbacks masking errors.
6. Retrieve-backed SQL must be patient-correlated (no cross-patient leakage).

## Audit of this iteration's diff
- QA-003 fix IMPROVES invariant 1: the FHIR→CQL type map moved from an inline dict in
  `inference.py` to the module-level `FHIR_TYPE_TO_CQL_TYPE` consumed by is-check lowering —
  single source of truth, no per-field hardcoding.
- All new SQL is AST-built (SQLSelect/SQLSubquery/SQLFunctionCall); no SQLRaw introduced.
- QA-001/QA-002 fixes keep patient correlation (correlated `_agg_src` subqueries; the
  correlation.py guard only skips subqueries with NO FROM clause, which cannot leak patients).
- Minor duplication: the structural UNNEST handler mirrors the backbone-array `_lt_` pattern
  (~40 lines); acceptable, consolidation can wait until a third caller appears.
- First/Last over unordered retrieves are nondeterministic by construction (CQL does not define
  retrieve ordering); the regression test compares order-insensitively — documented in test.
- No test-driven hacks observed; all fixes are class-level (bare retrieves, structural sources,
  string-family primitives), not fixture-specific.

## QA Enforcer Gate
QA was NOT lazy: spec text fetched from cql.hl7.org §9-b before logging; both execution paths
compared; literals AND retrieves probed; 4 real defects with minimal reproducers. No RETRY_QA.

## Empirical validation
- test_structural_type_parity.py 17/17; CQL unit 1612/1612; conformance 2832/2832 (ViewDef 144,
  FHIRPath 935, CQL 1706, DQM 47). No regressions.

## Issue summary
4 RESOLVED (QA-001 HIGH, QA-002 HIGH, QA-003 MEDIUM, QA-004 MEDIUM), 1 DEFERRED (QA-005 MEDIUM,
tagged-item value comparisons — needs per-element unwrap in comparison lowering). Zero open
non-terminal CRITICAL/HIGH/MEDIUM issues.

## Compression of handoffs
QA probed CQL 1.5 As/Is/Children/Descendants/Convert through parse→translate→DuckDB execution on
both backends; verified As null-on-mismatch, Is null-is-false, Children/Descendants null-in→null,
convert-null-when-impossible as spec-correct, and broke four surfaces (bare-retrieve First/Last/
singleton-from invalid SQL; per-element alias binding over Children/Descendants; FHIR string-family
`is String`; exists-over-list-alias SQL). Engineer fixed all four in the translator with AST-level
correlated/UNNEST lowering plus a data-driven type-family map, added 3 dual-path regression tests,
and held the 2832/2832 gate.

## Exit decision
iteration 1 ≥ min_iterations 1; no non-terminal CRITICAL/HIGH/MEDIUM issues → CLEAN exit
(workflow=null, exit_reason=CLEAN). QA-005 surfaced for the outer orchestrator/backlog.
