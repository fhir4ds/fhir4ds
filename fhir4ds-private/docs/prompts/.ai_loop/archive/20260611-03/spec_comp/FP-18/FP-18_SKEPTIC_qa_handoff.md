# QA Handoff - FP-18 / SKEPTIC
Chunk: FP-18 (FHIRPath)
Sections: §6.6 Math Operations; §6.7 Date/Time Arithmetic
Items: * (multiplication); / (division); + (addition); - (subtraction); div (truncated division); mod (modulo); & (string concatenation); + (dateTime addition); - (dateTime subtraction)
Command: python3 -m pytest fhir4ds/fhirpath/tests/unit/test_extension_fn.py -q --maxfail=1
Result: PASS

No issues found.
