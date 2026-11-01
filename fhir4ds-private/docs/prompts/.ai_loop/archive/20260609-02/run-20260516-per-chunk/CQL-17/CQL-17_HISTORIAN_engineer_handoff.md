# Engineer Handoff: CQL-17 HISTORIAN

## Triage

| Issue | Classification | Outcome |
| --- | --- | --- |
| QA-001 | Spec/conformance conflict | INTENDED |
| QA-002 | Parity/spec violation | RESOLVED |

## QA-001

The attempted endpoint-inclusive interval-point `properly includes` fix passed the synthetic probe but regressed official CQL conformance. The failing XML cases were:

- `TimeProperContainsFalse`
- `TimeProperInFalse`

Deep research was written to `fhir4ds-private/docs/prompts/.ai_loop/state/deep_research_findings.md`. The active repository target is the bundled official XML suite, so strict boundary behavior is preserved and documented in `extensions/cql/AGENTS.md`.

## QA-002

Fixed no-Python/browser-style C++ `intervalStartsSame` and `intervalEndsSame` semantics:

- compare effective `Start`/`End` boundaries, not raw low/high fields
- `starts` now requires equal effective starts and `end(left) <= end(right)`
- `ends` now requires equal effective ends and `start(left) >= start(right)`
- UDF wrappers return SQL NULL when required interval boundaries are missing

## Validation

- Fresh probe: `PYTHONPATH=/mnt/d/fhir4ds python3 .temp/qa/cql17_historian_probe.py` passed.
- Native C++: `./build/release/test/unittest "*cql*"` passed, 746 assertions.
- Interval cluster pytest passed, 80 tests.
- Official conformance passed, 2822/2822 with CQL 1706/1706.
- Bundled/native CQL extension SHA-256 matched: `a273b6cb4068e6661f5674b24440f6b31893fa68dbdfea3c275f2ac66e7ea608`.

## Changed Code Paths

- `extensions/cql/src/cql/interval.cpp`
- `extensions/cql/src/cql_extension.cpp`
- `extensions/cql/test/sql/cql.test`
- `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`
- `fhir4ds/cql/duckdb/tests/integration/test_interval_part3_parity.py`
- `fhir4ds/cql/duckdb/tests/test_interval_udfs.py`
- `fhir4ds/cql/duckdb/udf/interval.py`
- `extensions/cql/AGENTS.md`
- `.temp/qa/cql17_historian_probe.py`
