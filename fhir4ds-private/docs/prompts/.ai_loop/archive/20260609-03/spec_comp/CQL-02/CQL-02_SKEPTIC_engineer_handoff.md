# Engineer Handoff: CQL-02 SKEPTIC

Resolved 3 HIGH clinical type issues.

Changes made:
- `fhir4ds/cql/translator/expressions/_query.py`: clinical parameter `cql_type` metadata now participates in static clinical `is`/`as` resolution, so ValueSet/CodeSystem parameters satisfy `Vocabulary` while Code/Concept do not.
- `fhir4ds/cql/translator/expressions/_functions.py`: translated `ToConcept(List<Code>)` routes through `ToConceptFromList` instead of emitting an invalid `ToConcept(VARCHAR[])` call.
- `fhir4ds/cql/translator/expressions/_operators.py`: definitely-null operands in ValueSet/CodeSystem membership short-circuit to `FALSE` before terminology dispatch.
- `fhir4ds/cql/duckdb/udf/quantity.py` and `extensions/cql/src/cql/quantity.cpp`: `ToConcept` validates Code shape, rejects Quantity-like objects, propagates `Code.display` to `Concept.display`, and accepts list-shaped code inputs through the Python macro/native overload path.
- `extensions/cql/src/cql_extension.cpp`: native C++ now registers `ToConcept(VARCHAR[])` and `ToConceptFromList(VARCHAR[])`.

Validation:
- `python3 .temp/qa/cql02_skeptic_probe.py`: passed.
- Focused clinical/conversion pytest: `23 passed`.
- Native CQL sqllogictest: `776 assertions passed`.
- Full conformance: `2822/2822`.
