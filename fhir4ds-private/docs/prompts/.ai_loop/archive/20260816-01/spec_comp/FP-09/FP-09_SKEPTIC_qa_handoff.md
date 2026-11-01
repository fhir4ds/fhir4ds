# QA Handoff - FP-09 / SKEPTIC
Chunk: FP-09 (FHIRPath)
Sections: §5.6.1-§5.6.5 String Manipulation (Search)
Items: indexOf(substring); substring(start, [length]); startsWith(prefix); endsWith(suffix); contains(substring)
Command: python3 -m pytest fhir4ds/fhirpath/tests/unit/test_extension_fn.py -q --maxfail=1
Result: PASS

No issues found.
