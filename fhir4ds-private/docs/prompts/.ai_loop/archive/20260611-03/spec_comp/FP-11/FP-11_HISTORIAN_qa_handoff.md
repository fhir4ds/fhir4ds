# QA Handoff - FP-11 / HISTORIAN
Chunk: FP-11 (FHIRPath)
Sections: §5.7 Math (STU)
Items: abs(); ceiling(); exp(); floor(); ln(); log(base); power(exponent); round([precision]); sqrt(); truncate()
Command: python3 -m pytest fhir4ds/fhirpath/tests/unit/test_extension_fn.py -q --maxfail=1
Result: PASS

No issues found.
