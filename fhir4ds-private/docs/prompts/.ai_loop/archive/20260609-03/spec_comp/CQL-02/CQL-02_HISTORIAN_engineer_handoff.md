# Engineer Handoff: CQL-02 HISTORIAN

Resolved:
- `QA-001` HIGH, CQL ValueSet `codesystems` override support.

Root cause:
- `parse_valueset_definition()` accepted ValueSet id/version but did not parse
  the optional CQL 1.5 `codesystems { ... }` clause.
- `ValueSetDefinition` and `SQLTranslationContext` did not preserve
  CodeSystem override names, so structured `System.ValueSet` JSON had no way to
  emit the trial-use `codesystems List<CodeSystem>` element.

Fix:
- Added `ValueSetDefinition.codesystems`.
- Parsed non-empty ValueSet `codesystems { ... }` lists, including quoted and
  qualified identifiers, while rejecting empty lists and trailing commas.
- Registered CodeSystems before ValueSets in translator setup so ValueSet
  overrides can resolve to structured CodeSystem id/name/version entries.
- Added `SQLTranslationContext.valueset_codesystems` and propagated it through
  include-result context copying.
- Extended `_clinical_valueset_literal()` to emit `codesystems` JSON entries.
- Added parser and clinical type parity tests.

Validation:
- `PYTHONPATH=. python3 .temp/qa/cql02_historian_probe.py` passed.
- `PYTHONPATH=. python3 -m pytest fhir4ds/cql/tests/unit/test_parser.py fhir4ds/cql/duckdb/tests/integration/test_clinical_type_parity.py -q`:
  91 passed.
- `PYTHONPATH=. python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_conversion_function_parity.py fhir4ds/cql/duckdb/tests/integration/test_clinical_operator_parity.py -q`:
  13 passed.
- `PYTHONPATH=. python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"`:
  ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall
  2822/2822.
