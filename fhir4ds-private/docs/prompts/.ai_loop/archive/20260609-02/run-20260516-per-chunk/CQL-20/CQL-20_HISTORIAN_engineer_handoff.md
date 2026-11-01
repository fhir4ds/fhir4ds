# Engineer Handoff - CQL-20 HISTORIAN Aggregate Functions

Resolved issues:
- `QA-001`: `_wrap_list_aggregate()` now only injects patient correlation for
  CTE/retrieve-backed sources. Structural list-literal query sources are left
  uncorrelated. Boolean query-source aggregates now wrap `bool_and`/`bool_or`
  in CQL defaults, preserving `AllTrue` true and `AnyTrue` false when no
  non-null Boolean exists.
- `QA-002`: added pure SQL `CQLListMode(lst)` and routed translated list
  `Mode` through it. Query-source `Mode` now aggregates rows into `LIST(_val)`
  and applies the same helper. Tied most-frequent values return NULL across
  forced Python fallback, native-loaded registration, and no-Python/browser
  macro execution.

Code/test changes:
- `fhir4ds/cql/translator/expressions/_functions.py`
- `fhir4ds/cql/duckdb/macros/list.py`
- `fhir4ds/cql/duckdb/tests/integration/test_aggregate_parity.py`
- `fhir4ds/cql/tests/unit/test_v2_expressions.py`
- `extensions/cql/AGENTS.md`
- `.temp/qa/cql20_historian_probe.py`

Validation:
- Fresh probe: `python3 .temp/qa/cql20_historian_probe.py` passed.
- Focused aggregate/macro/list tests: `119 passed`.
- Targeted unit + aggregate parity rerun: `6 passed`.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.
- Full pytest: `7220 passed, 5 skipped, 9 warnings`.
- Targeted `git diff --check`: clean.
