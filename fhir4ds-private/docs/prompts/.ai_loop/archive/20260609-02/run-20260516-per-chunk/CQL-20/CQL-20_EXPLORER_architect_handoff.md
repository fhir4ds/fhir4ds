# Architect Handoff — CQL-20 EXPLORER

## Golden Standard

Wrote `.temp/architect/golden_standard.md` with aggregate-specific invariants:
CQL direct aggregate names are list-signature surfaces, translated query-form
row aggregation must call DuckDB row aggregates explicitly, `Min`/`Max` must
preserve non-numeric comparison domains, and all emitted aggregate SQL must run
in forced Python fallback, native-loaded, and no-Python/browser-style paths.

## Audit Result

Structural status: PASSED.

The remediation cleanly separates public CQL list macros from translated SQL
row aggregation. `Median`/`StdDev`/`Variance` direct macros now implement list
semantics, while query-form statistical aggregates use `system.*` row aggregate
names to avoid macro capture. The `Min`/`Max` fix is appropriately narrow:
numeric-only casts remain for numeric aggregates, and comparison-domain
aggregates no longer erase Date, Time, or String values. No hardcoded test data,
FHIR profile assumptions, or cross-layer shortcuts were introduced.

## QA Enforcer Gate

QA was sufficient. The fresh probe combined direct public helper abuse,
translated query-shaped list sources, and three DuckDB execution surfaces. It
found two real medium spec violations beyond happy-path aggregate coverage.
`RETRY_QA` remains `false`.

## Verified

- `python3 .temp/qa/cql20_explorer_probe.py`
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_aggregate_parity.py fhir4ds/cql/duckdb/tests/test_macros_tier1.py -q --tb=short` -> 72 passed
- `python3 -m pytest fhir4ds/cql -q --tb=short` -> 4986 passed, 5 skipped, 6 warnings
- `python3 conformance/scripts/run_all.py` -> 2822/2822, 100%
- `python3 -m pytest -q --tb=short` -> 7221 passed, 5 skipped, 9 warnings
- Targeted `git diff --check` -> clean

## State

`evolution.json` is closed with `workflow: null`, `exit_reason: "CLEAN"`,
`audit_status: "PASSED"`, `RETRY_QA: false`, and `QA-001`/`QA-002` tombstoned
as `VERIFIED`.
