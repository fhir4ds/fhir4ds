# QA Handoff - FP-06 / EXPLORER
Chunk: FP-06 (FHIRPath)
Sections: §5.5.1 iif; §5.5.2 Boolean Conversion; §5.5.3 Integer Conversion
Items: iif(criterion, true-result, otherwise-result); toBoolean(); convertsToBoolean(); toInteger(); convertsToInteger()
Command: python3 -m pytest fhir4ds/fhirpath/tests/unit/test_extension_fn.py -q --maxfail=1
Result: PASS

No issues found.
