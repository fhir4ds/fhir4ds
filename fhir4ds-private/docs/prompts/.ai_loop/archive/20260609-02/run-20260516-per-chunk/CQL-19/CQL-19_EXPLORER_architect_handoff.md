# Architect Handoff: CQL-19 EXPLORER List Operators Part 2

## Audit Result

PASSED. One medium spec issue was found by QA and resolved. No additional
architecture findings were opened.

## Structural Assessment

The fix preserves the correct abstraction boundary: generic list helpers still
own ordinary CQL list equality, while temporal uncertainty is routed through
separate temporal helper macros only when the translator has AST-level evidence
that both operands are temporal. This avoids reclassifying string literals that
look like times and keeps the public no-Python/browser-style path aligned with
forced Python fallback and native-loaded registration.

The new coverage exercises translated CQL and direct helper SQL on all three
DuckDB execution surfaces. QA was sufficient for EXPLORER: it chained list
operators with partial temporal precision, null handling, nested list outputs,
Quantity union/dedup, and `SingletonFrom` assertion behavior.

## Verified

- `.temp/architect/golden_standard.md` written with CQL-19 EXPLORER invariants.
- `.temp/qa/cql19_explorer_probe.py` passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_list_part2_parity.py fhir4ds/cql/duckdb/tests/test_list_udfs.py -q --tb=short` -> 54 passed.
- Official CQL list category plus list parity/UDF cluster -> 271 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py` -> 2822/2822.
- `python3 -m pytest -q --tb=short` -> 7218 passed, 5 skipped, 9 warnings.
- Targeted `git diff --check` on changed files -> clean.

## Recommended Fix Order

No further fixes are required for this inner run. `RETRY_QA` remains false.
