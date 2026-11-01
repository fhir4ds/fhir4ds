# QA Handoff - CQL-21 HISTORIAN

Fresh HISTORIAN pass covered the CQL-21 Clinical Operators scope from the active
state: age precision helpers, `CalculateAgeIn*`, Code/Concept equality and
equivalence, CodeSystem membership, ValueSet membership, and `ExpandValueSet`.

Normative source consulted: CQL 1.5.3 Appendix B. The relevant language says
the age operators calculate patient age at the requested precision, `in
CodeSystem` returns false for null code arguments, and `ExpandValueSet(ValueSet)`
returns `List<Code>` and is used as the implicit conversion from a ValueSet
reference to a list of Code values.

Fresh validation performed:
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_clinical_operator_parity.py fhir4ds/cql/duckdb/tests/integration/test_clinical_type_parity.py -q` -> 13 passed.
- `.temp/qa/cql21_historian_probe.py` found one current bug before remediation.

Finding:
- `QA-001` MEDIUM: Direct public DuckDB `Count(ExpandValueSet(?))` counts the
  expanded list as one scalar. Both forced Python fallback and native/C++
  connections return `ExpandValueSet(?)` as a `VARCHAR[]` containing two codes
  and `list_count(ExpandValueSet(?)) = 2`, but `Count(ExpandValueSet(?)) = 1`.
  Expected result is 2 because `ExpandValueSet(ValueSet)` is a list-returning
  CQL function.
