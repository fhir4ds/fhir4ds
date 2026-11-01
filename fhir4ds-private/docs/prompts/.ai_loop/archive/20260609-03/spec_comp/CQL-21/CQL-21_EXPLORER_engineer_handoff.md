# Engineer Handoff — CQL-21 EXPLORER

Resolved `CQL21-EXPLORER-001`.

Changes:
- `fhir4ds/cql/duckdb/udf/valueset.py`: Python-registered `ExpandValueSet` macro now resolves structured ValueSet JSON as `id|version` when `version` is present.
- `fhir4ds/cql/duckdb/macros/valueset.py`: SQL-only/no-Python `ExpandValueSet` macro now uses the same `id|version` lookup.
- `fhir4ds/cql/duckdb/tests/integration/test_clinical_operator_parity.py`: added versioned `ExpandValueSet` plus membership parity across forced Python fallback, native-loaded, and no-Python runtimes.
- `.temp/qa/cql21_explorer_probe.py`: fresh reproducer and verification probe.
- `extensions/cql/AGENTS.md`: recorded the versioned ValueSet expansion invariant.

Verification:
- `.temp/qa/cql21_explorer_probe.py`: PASS.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_clinical_operator_parity.py -q`: 12 passed.
- `python3 conformance/scripts/run_cql.py`: 1706/1706 passed.
- `python3 conformance/scripts/run_all.py`: 2822/2822 passed.

No open remediation items remain for this pass.
