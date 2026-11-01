# QA Handoff - FP-07 / SKEPTIC
Chunk: FP-07 (FHIRPath)
Sections: §5.5.4 Date Conversion; §5.5.5 DateTime Conversion; §5.5.6 Decimal Conversion
Items: toDate(); convertsToDate(); toDateTime(); convertsToDateTime(); toDecimal(); convertsToDecimal()
Command: python3 -m pytest fhir4ds/fhirpath/tests/unit/test_extension_fn.py -q --maxfail=1
Result: PASS

No issues found.
