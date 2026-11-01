# QA Handoff - FP-13 / HISTORIAN
Chunk: FP-13 (FHIRPath)
Sections: §6.1 Equality
Items: = (Equals) incl. Quantity and Date/Time equality; ~ (Equivalent) incl. Quantity, Date/Time, String equivalence; != (Not Equals); !~ (Not Equivalent)
Command: python3 -m pytest fhir4ds/fhirpath/tests/unit/test_extension_fn.py -q --maxfail=1
Result: PASS

No issues found.
