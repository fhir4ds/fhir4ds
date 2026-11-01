# Architect Handoff — CQL-21 HISTORIAN

Golden standard: clinical operators stay on clinical semantic paths; terminology data lives in runtime caches/tables, not hardcoded translator lists; public CQL surfaces emitted by translated SQL must work in forced Python fallback, native-loaded, and no-Python runtimes where applicable.

Audit result: `CQL21-HISTORIAN-001` is structurally resolved. The translator fix classifies static clinical `ListExpression` operands before generic list containment, which keeps CodeSystem/ValueSet membership at the semantic operator boundary. The no-Python `ExpandValueSet` fix belongs in macro registration because it is a SQL-only list-returning public surface backed by `valueset_codes`, matching the existing Python registration shape without adding clinical code constants.

QA quality: adequate. The HISTORIAN pass exercised the overload matrix missed by scalar-focused tests and verified translated CQL plus direct no-Python macro behavior.

Validation:
- `.temp/qa/cql21_historian_probe.py`: PASS.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_clinical_operator_parity.py -q`: 11 passed.
- `python3 conformance/scripts/run_cql.py`: 1706/1706 passed.
- `python3 conformance/scripts/run_all.py`: 2822/2822 passed.

No retry requested. No open findings remain for this pass.
