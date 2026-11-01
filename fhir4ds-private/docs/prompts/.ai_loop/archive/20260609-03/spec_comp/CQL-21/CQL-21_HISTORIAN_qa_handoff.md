# QA Handoff — CQL-21 HISTORIAN

Scope: CQL clinical operators from CQL Reference v1.5.3: Age/AgeAt/CalculateAge/CalculateAgeAt, Code/Concept equality and equivalence, CodeSystem membership, `ExpandValueSet(ValueSet)`, and ValueSet membership.

Spec anchors checked:
- Age/AgeAt operators are shorthand for CalculateAge variants and return null when birthDate/asOf is null.
- Clinical `=` uses tuple equality for Code/Concept.
- Clinical `~` ignores Code display/version and compares Concepts by non-empty Code intersection.
- `in` against CodeSystem/ValueSet supports String, Code, Concept, and list overloads; null code arguments are false.
- `ExpandValueSet(ValueSet)` returns `List<Code>` and null for null input.

Fresh probe:
- `.temp/qa/cql21_historian_probe.py`

Finding:
- `CQL21-HISTORIAN-001` HIGH: static `List<Code>`, `List<string>`, and `List<Concept>` membership in CodeSystem/ValueSet did not lower through clinical membership semantics. CodeSystem list cases fell through to generic list containment against the CodeSystem JSON literal; ValueSet list cases unnested raw Code JSON/string elements and passed them to `in_valueset` as if they were resources. The same probe found `ExpandValueSet` was unavailable in no-Python/browser-style runtime because it was only registered by Python valueset UDF registration.

Validation during QA/fix:
- Fresh probe passes.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_clinical_operator_parity.py -q`: 11 passed.
