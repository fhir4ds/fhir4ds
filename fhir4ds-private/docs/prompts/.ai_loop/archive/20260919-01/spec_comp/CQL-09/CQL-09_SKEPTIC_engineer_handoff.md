# Engineer Handoff — CQL-09 Comparison Operators (iteration 1)

## QA-001 (MEDIUM) — RESOLVED
`{1, null} = {1, 2}` returned false; CQL 1.5 §9.4 Equal (list) requires null (one-sided null element is uncertain; only null-null pairs are "considered equal").

Fix: `fhir4ds/cql/duckdb/macros/list.py` — `CQLListEqualEq` and `CQLListEqualTemporalEq` now wrap element comparisons in a CASE that maps null-null → TRUE and one-sided null → NULL (uncertain) before the IS FALSE / IS NULL existence checks. `CQLListElementEqual` itself is unchanged: `in`/`contains`/`except`/`distinct` consumers keep the pinned doctrine that a one-sided null is NOT contained (False), which the first cut violated (`{1, null, 3} except {null}` regressed to [] and `5 in {1, null}` flipped to null). Shared by both registrations; native and Python paths verified.

## QA-002 (MEDIUM) — RESOLVED
`Interval[null, 3] = Interval[1, 3]` / `Interval[1, 3] = Interval[1, null]` returned false; CQL 1.5 §9.4 Equal (interval, via Start/End null propagation) requires null for a one-sided CLOSED null bound (unknown), while a one-sided OPEN null bound is unbounded and definitely unequal (False — pinned doctrine from the interval chunk, re-verified).

Fix (dual-engine, lockstep):
- Python: `fhir4ds/cql/duckdb/udf/interval.py::_interval_bound_equals_nullable` — one-sided null now checks the null side's closed flag: closed → None (uncertain), open → False. `_bounds_equal` unchanged.
- Native: `extensions/cql/src/cql/interval.cpp::Interval::equals_nullable` — same closed/open distinction using `low_closed`/`high_closed` of the null-bound side.
- Extension rebuilt (md5 `fa873077f0573cc9cbd003247dab916e`) and deployed to the repo bundle `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension` and site-packages copy; no ~/.duckdb cache copy existed. Re-verified through fresh no-Python LOAD of the rebuilt binary.

## QA-003 (LOW) — UNCONFIRMED (terminal, no fix)
Spec erratum: CQL 1.5 examples `ListNotEqualIsNull` and `DateTimeWithMillisecondsEqualIsNull` contradict the normative algorithm text (and, for the list example, the adjacent `ListEqualIsTrue` example). Implementation follows the algorithm; documented in AGENTS.md.

## Regression coverage
New test `test_cql_null_uncertainty_preserved_in_list_and_interval_equality` in `fhir4ds/cql/duckdb/tests/integration/test_comparison_operator_parity.py` (9 cases × py+cpp, incl. both-null → true, `~` never-null, `!=` null propagation).

## Validation
- Focused suites: comparison/list/interval parity + list UDF unit tests — 123 passed.
- Full conformance gate: ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, OVERALL 2832/2832 — baseline held, zero regressions.

## Environment notes
- `make release` in extensions/cql takes ~10 min; the first build raced my source refinement — always verify native behavior through a fresh LOAD before claiming a C++ fix (per GLOBAL_RULES post-build verification).
