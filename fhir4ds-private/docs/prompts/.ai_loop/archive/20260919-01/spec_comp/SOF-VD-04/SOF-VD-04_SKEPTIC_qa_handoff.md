# QA Handoff — SOF-VD-04 (SKEPTIC), iteration 1

Chunk: ViewDefinition.select.column.{collection,type,tag}.

## Probed (native + Python fallback, parity-checked)
- collection default false when unset; runtime error on multiple values for non-collection columns (both engines, PARITY). Multi-value output = DuckDB LIST (`list_transform` element casts for primitive types; empty list for absent paths; singleton list for singletons).
- collection=true type mismatch (string elements declared integer / date declared boolean) errors at runtime with the declared-type message, both engines, PARITY.
- type URI handling: relative names normalize ('string', 'HumanName', 'Quantity'); full SD URIs strip the prefix; fragment element-ID URIs ('http://hl7.org/fhir/StructureDefinition/Observation#Observation.referenceRange') normalize to 'Observation.referenceRange'; malformed URIs ('not a uri!', '', 'string ') rejected; unknown relative URIs ('unknown-type', System 'String') rejected at generation with the supported-type list.
- Type mismatch reporting: declared integer vs string code, declared boolean vs date → runtime error, PARITY. Non-primitive output with type unset → runtime error "type unset; non-primitive outputs require column.type", PARITY (collection and non-collection). Correctly typed non-primitive (HumanName/CodeableConcept, incl. full URI and element-ID form) emits JSON representation.
- tag: 0..* accepted; required non-empty name+value enforced; tag-as-object/string/int-item rejected; plural 'tags' rejected; round-trip to_dict preserves tags; duplicate tag names allowed (spec-silent); ansi/type=INTEGER tag on a string column does NOT change output (tags are hints) — PARITY.
- collection non-boolean (string "true", explicit null) rejected at parse.
- Official fixtures: no spec_tests fixture exercises column.tag; collection.json covered by suite (baseline 1171/1171 passed pre-fix, incl. 144 spec conformance).

## Issues
- QA-001 (MEDIUM, OPEN): unknown keys inside column objects and tag objects silently accepted; reference schema sets additionalProperties:false; inconsistent with targeted 'tags' rejection.
- QA-002 (LOW, OPEN): element-ID column.type whose leading resource segment differs from ViewDefinition.resource (e.g. 'Observation.referenceRange' in a Patient view) never reported as a type mismatch although statically detectable.

Probes: /mnt/d/fhir4ds/.temp/qa/probe.py
