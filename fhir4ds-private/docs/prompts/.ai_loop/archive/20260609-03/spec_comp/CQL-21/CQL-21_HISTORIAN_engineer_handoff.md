# Engineer Handoff — CQL-21 HISTORIAN

Resolved `CQL21-HISTORIAN-001`.

Changes:
- `fhir4ds/cql/translator/expressions/_operators.py`: extended clinical `in` lowering so static `ListExpression` operands flatten through Code/Concept entries or string codes before CodeSystem and ValueSet membership handling. CodeSystem list membership now mirrors scalar clinical membership; ValueSet list membership now emits an OR chain of synthetic Code resources into `in_valueset`.
- `fhir4ds/cql/duckdb/macros/valueset.py`: added SQL-only `ExpandValueSet(vs)` macro backed by a `valueset_codes` table.
- `fhir4ds/cql/duckdb/macros/__init__.py`: registered the ValueSet macro in `register_all_macros` so no-Python runtimes receive it.
- `fhir4ds/cql/duckdb/tests/integration/test_clinical_operator_parity.py`: added static list membership parity and no-Python `ExpandValueSet` coverage.
- `extensions/cql/AGENTS.md`: recorded the clinical list membership and `ExpandValueSet` no-Python invariant.

Verification:
- `.temp/qa/cql21_historian_probe.py`: PASS.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_clinical_operator_parity.py -q`: 11 passed.

No open remediation items remain for this pass.
