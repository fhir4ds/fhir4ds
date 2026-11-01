# Architect Handoff — CQL-15 EXPLORER iteration 1 (2026-08-22)

## Scope
Scoped structural audit of the iteration's changes: interval-expression
recognition (`_temporal_intervals.py`, `_functions.py::_translate_expand`),
expand boundary semantics (`udf/interval.py::_expand_temporal/_expand_time`,
`cql_extension.cpp::ExpandTemporalInterval/ExpandTimeInterval`), and the new
regression tests.

## Golden-standard invariants checked
1. Operand-type recognition must be by EXPRESSION CLASS (AST/SQL node shape),
   never by literal value or test-case string — PASS: the LIST_EXTRACT
   recognizer checks source node kinds (intervalFromBounds/Except/Intersect/
   Union, SQLList/SQLArray elements, from_json(collapse_intervals[_per])),
   recursing generically; no case-specific constants.
2. Engine parity: translator-level fixes must serve both engines; UDF-level
   semantics must be mirrored py/native and the binary rebuilt+md5-deployed —
   PASS (deployed md5 98a8c8583ed41359edfe929c03869d83; 21/21 dual+no-py
   parity tests; 370 integration tests).
3. Reference/fixtures outrank prose: the DBCG Java reference numeric-grid
   behavior was preserved, and the official ExpandPerHourOpen fixture
   (regression caught at 1704/1706 during validation) drove the correct
   low-only truncation semantics — PASS.
4. No silent fallbacks / test hacks: the two new tests assert real spec
   expectations; the single normalization in the QA-001 test is documented as
   a pre-existing py-vs-pure-C++ JSON quoting convention, not masked behavior
   (logged below as a LOW observation).
5. DQM sensitivity: interval recognition changes are DQM-sensitive per
   HISTORIAN CMS128 history — verified: DQM 47/47 on the fresh master gate.

## Findings
- No new CRITICAL/HIGH/MEDIUM issues.
- LOW observation (logged, not fixed — pre-existing transport convention):
  `intervalExcept` serializes numeric `low` as JSON number in the Python UDF
  and as string in the pure-C++ serializer (`{"low": 6}` vs `{"low": "6"}`).
  Both engines' SQL-level consumers key on the field, but downstream numeric
  consumers must parse defensively. Candidate follow-up: unify C++/py bound
  serialization.
- QA quality gate: EXPLORER QA was thorough (~130 dual-engine probes, checked
  against cached CQL 1.5 §9 text AND the HL7 DBCG Java reference engine; both
  filed issues reproduced and were root-causeable). No RETRY_QA. One QA
  expectation was miscalibrated (`(collapse ... per 2)[1]` — per merges the
  list, index 1 legitimately null); remediation documented rather than coded
  around.

## Validation (fresh, after final edit)
- Master gate: ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47 — OVERALL 2832/2832 (100%).
- CQL integration battery: 370 passed, 5 skipped.
- Interval part1 parity file: 21/21 (incl. 2 new dual-engine tests).

## State
Both iteration issues RESOLVED (terminal). Zero non-terminal
CRITICAL/HIGH/MEDIUM at iteration 1 ≥ min_iterations 1 → CLEAN exit
recommended; workflow set to null, control returns to the outer spec
compliance orchestrator per config.notes.
