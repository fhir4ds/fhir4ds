# Engineer Handoff - CQL-22 SKEPTIC

Resolved issues:
- QA-001 HIGH: `Message` no longer drops nonliteral severity expressions. Dynamic severity parameters and definition references now reach `CQLMessage`; bare inlined severity identifiers such as CMS `ErrorLevel` normalize to the existing session-parameter surface instead of becoming unbound SQL columns.
- QA-002 MEDIUM: public DuckDB `CQLMessage` now preserves `source` type via a SQL macro around `error(...)`, fixing numeric and Boolean source behavior.

Files changed by this remediation:
- `fhir4ds/cql/translator/expressions/_functions.py`
- `fhir4ds/cql/duckdb/udf/math.py`
- `fhir4ds/cql/duckdb/tests/integration/test_message_parity.py`
- `AGENTS.md`
- `.ai_loop/state/deep_research_findings.md`

Validation:
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_message_parity.py -q` -> 4 passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py -q` -> 8 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py | grep ...` -> ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
- `python3 -m pytest fhir4ds/ -x --tb=short | tail -n 50` -> 7232 passed, 5 skipped, 9 warnings.

Deep research note: the first full conformance attempt exposed a DQM regression for included-library `ErrorLevel`; details are appended in `.ai_loop/state/deep_research_findings.md`.
