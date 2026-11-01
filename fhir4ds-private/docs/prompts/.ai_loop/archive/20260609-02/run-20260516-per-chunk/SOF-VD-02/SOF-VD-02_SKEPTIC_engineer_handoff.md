## SOF-VD-02 Engineer Handoff - Remediation

Resolved issues:

- `SOF-VD-02-QA-001`: enforced SQL-on-FHIR `sql-name` validation for `ViewDefinition.constant.name` at both parser and `Constant.from_dict()` boundaries.
- `SOF-VD-02-QA-002`: enforced `constant.value[x]` as exactly one supported non-null value choice; rejected unknown `value*` fields and multiple value choices; added explicit `valueCanonical` and `valueInteger64` support.

Implementation notes:

- Added shared `CONSTANT_NAME_RE`, `CONSTANT_VALUE_FIELD_TYPES`, and `_extract_constant_value()` in `fhir4ds/viewdef/types.py`.
- Updated `fhir4ds/viewdef/parser.py` to wrap shared validation failures as `ParseError`.
- Kept historical `valueCoding` and `valueCodeableConcept` support to preserve existing public API/tests, while still enforcing exactly-one behavior across all accepted value choices.

Validation:

- `python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py::TestConstantParsing fhir4ds/viewdef/tests/unit/test_constants.py::TestEdgeCases -q` -> 24 passed
- `python3 -m pytest fhir4ds/viewdef/tests -q` -> 715 passed
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_viewdef.py` -> 134/134 passed
- `python3 -m pytest fhir4ds/ -q --tb=short` -> 7252 passed, 5 skipped
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py` -> overall 2822/2822, ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47

New issues discovered: none.
