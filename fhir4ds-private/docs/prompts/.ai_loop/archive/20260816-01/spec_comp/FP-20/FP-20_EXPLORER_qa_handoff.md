# QA Handoff - FP-20 / EXPLORER
Chunk: FP-20 (FHIRPath)
Sections: §9 Environment Variables; §10 Types and Reflection; §11 Type Safety; §12 Formal Specifications
Items: Environment variable access (%context, %resource, etc.); Model information; SimpleTypeInfo; ClassInfo; ListTypeInfo; TupleTypeInfo; Type safety rules; Formal syntax (ANTLR); URI and media types
Command: python3 -m pytest fhir4ds/fhirpath/tests/unit/test_extension_fn.py -q --maxfail=1
Result: PASS

No issues found.
