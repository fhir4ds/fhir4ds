# CQL-05 EXPLORER Engineer Handoff

## Resolved Issues

- Added structural list type checks for `cqlChildren`/`cqlDescendants` outputs so `List<Any>` and typed primitive list assertions work without falling into FHIR resource probing.
- Preserved Date, DateTime, Time, and Long identity for tuple values passed through `Children()`/`Descendants()` by using internal CQL type tags.
- Added runtime JSON shape checks for structural Code/Concept child values while preserving path-aware FHIR resource behavior for `Observation.value as Concept`.
- Implemented and registered `ToConceptFromList(VARCHAR[])` and `ConceptToListCode(VARCHAR)` for CQL `convert` between `List<Code>` and `Concept`.
- Made `test_structural_type_parity._python_only_connection()` register FHIRPath Python UDFs directly and skip native extension loading.
- Added Python fallback FHIRPath choice-field assertion handling for simple `value.is(Type)` and `value.as(Type)` expressions, including resource-type-prefixed `Observation.value...`.
- Adjusted Code/Concept equivalence translation so `O.value as Concept ~ "Code"` compiles to `coding_matches(O.resource, 'valueCodeableConcept', ...)`, preserving DQM value set behavior.

## Files Changed In This Pass

- `fhir4ds/cql/translator/expressions/_functions.py`
- `fhir4ds/cql/translator/expressions/_operators.py`
- `fhir4ds/cql/translator/expressions/_query.py`
- `fhir4ds/cql/duckdb/udf/list.py`
- `fhir4ds/cql/duckdb/udf/quantity.py`
- `fhir4ds/cql/duckdb/udf/valueset.py`
- `fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py`
- `fhir4ds/cql/duckdb/tests/integration/test_clinical_type_parity.py`
- `fhir4ds/fhirpath/duckdb/udf.py`

## Notes

The forced Python fallback helper now asserts that `fhirpath_predicate` is absent. Keep that guard in parity tests so future "Python-only" tests cannot silently load the native extension.
