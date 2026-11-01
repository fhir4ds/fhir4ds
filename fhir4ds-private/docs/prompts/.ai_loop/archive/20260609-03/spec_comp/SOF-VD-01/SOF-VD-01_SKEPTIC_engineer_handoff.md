# Engineer Handoff: SOF-VD-01 SKEPTIC

Resolved:
- `SOF-VD-01-SKEPTIC-001`: `ViewDefinition.profile` now uses a shared canonical-array validator instead of the prior generic string-list handling.

Changed:
- `fhir4ds/viewdef/types.py`: added `validate_canonical_array()` and reused it for `ViewDefinition.profile`, `ViewDefinition.meta.profile`, and `ViewDefinition.to_dict()`.
- `fhir4ds/viewdef/parser.py`: root `profile` now parses through canonical-array validation.
- `fhir4ds/viewdef/generator.py`: direct dataclass `ViewDefinition.profile` is validated before SQL generation.
- `fhir4ds/viewdef/tests/unit/test_parser.py`: added malformed-profile rejection and valid version-suffixed canonical coverage.
- `fhir4ds/viewdef/tests/unit/test_generator.py`: added direct dataclass profile guard coverage.
- `.temp/qa/sof_vd01_skeptic_probe.py`: fresh probe for parser/generator rejection, shared-table `resourceType` filtering, and zero/multiple row behavior across fallback and native FHIRPath paths.

Validation:
- Fresh SOF-VD-01 SKEPTIC probe: PASS.
- Focused parser/generator tests: 7 passed.
- ViewDefinition tests: 900 passed.
- ViewDefinition conformance: 134/134.
- Full conformance: 2822/2822.

No new issues were discovered during remediation.
