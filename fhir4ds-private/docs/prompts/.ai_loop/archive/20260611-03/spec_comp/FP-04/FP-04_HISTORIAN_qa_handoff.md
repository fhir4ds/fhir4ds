# QA Handoff - FP-04 / HISTORIAN
Chunk: FP-04 (FHIRPath)
Sections: §5.2 Filtering and Projection
Items: where(criteria); select(projection); repeat(projection); ofType(type)
Command: python3 -m pytest fhir4ds/fhirpath/tests/unit/test_extension_fn.py -q --maxfail=1
Result: PASS

No issues found.
