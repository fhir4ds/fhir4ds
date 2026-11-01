# QA Handoff - FP-05 / HISTORIAN
Chunk: FP-05 (FHIRPath)
Sections: §5.3 Subsetting; §5.4 Combining
Items: [index] indexer; single(); first(); last(); tail(); skip(num); take(num); intersect(other); exclude(other); union(other); combine(other)
Command: python3 -m pytest fhir4ds/fhirpath/tests/unit/test_extension_fn.py -q --maxfail=1
Result: PASS

No issues found.
