# Architect Handoff — CQL-15 iteration 1 (HISTORIAN), 2026-08-21

## Structural health
Five issues closed (2 HIGH spec violations, 1 HIGH regression, 1 MEDIUM engine
divergence, 1 LOW deferred parser gap). All fixes are spec-grounded against
cql.hl7.org §9 and the reference engine source, dual-engine (Python + native,
rebuilt binary deployed, md5 74a3a9d6), and covered by a new triple-engine
regression test. Master gate rerun fresh: 2832/2832.

## Audit findings
- The QA-005 CMS128 regression exposed a structural hazard: JSON-array-string
  UDF names are recognized by name in at least four scattered translator sites
  (_JSON_LIST_FUNCS, _query.py list_transform set, _lists.py First/Last, plus
  comments in _query.py 4472/4817). Adding a UDF without updating every site
  silently changes aggregate lowering (list_sum → SQL SUM) and can break
  measure SQL at bind time. Logged as Architecture Drift (LOW, recommend a
  single canonical constant, e.g. in expressions/_utils.py next to
  _is_list_returning_sql). Not fixed inline per audit protocol.
- The CQL-15 SKEPTIC handoff claimed a passing gate that the final tree did not
  satisfy. Process drift: chunk engineers must rerun the master gate after the
  LAST edit, not cite an earlier run. Noted in AGENTS.md doctrine.
- Fix quality otherwise conforms to the golden standard: no SQLRaw, no silent
  fallbacks, layering preserved (translator routing fix vs UDF semantics fix in
  the right layers), native and Python mirror each other's algorithm.

## QA enforcement gate
QA (HISTORIAN) was thorough: 100+ fresh dual-engine probes beyond the SKEPTIC
battery, spec verified against live reference source, prior fixes re-verified
(18/18 pins), and the inherited CMS128 regression caught at the recovery gate
and root-caused (not papered over). No RETRY_QA.

## Recommended fix order (next iteration, if any)
1. (LOW drift) Centralize JSON-list UDF name recognition in one constant.
2. (Deferred QA-004) negative `per` quantity literal — parser support only if a
   spec/reference mandate emerges.

## State
All issues terminal (RESOLVED x4, DEFERRED x1). Clean exit at iteration 1
(>= min_iterations 1, zero non-terminal CRITICAL/HIGH/MEDIUM).
