# QA Handoff - FP-03 / SKEPTIC
Chunk: FP-03 (FHIRPath)
Sections: §5.1 Existence
Items: empty(); exists([criteria]); all(criteria); allTrue(); anyTrue(); allFalse(); anyFalse(); subsetOf(other); supersetOf(other); count(); distinct(); isDistinct()
Command: python3 -m pytest fhir4ds/fhirpath/tests/unit/test_extension_fn.py -q --maxfail=1
Result: PASS

No issues found.
