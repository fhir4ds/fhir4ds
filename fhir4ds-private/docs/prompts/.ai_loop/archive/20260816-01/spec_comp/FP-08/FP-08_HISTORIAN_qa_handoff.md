# QA Handoff - FP-08 / HISTORIAN
Chunk: FP-08 (FHIRPath)
Sections: §5.5.7 Quantity Conversion; §5.5.8 String Conversion; §5.5.9 Time Conversion
Items: toQuantity([unit]); convertsToQuantity([unit]); toString(); convertsToString(); toTime(); convertsToTime()
Command: python3 -m pytest fhir4ds/fhirpath/tests/unit/test_extension_fn.py -q --maxfail=1
Result: PASS

No issues found.
