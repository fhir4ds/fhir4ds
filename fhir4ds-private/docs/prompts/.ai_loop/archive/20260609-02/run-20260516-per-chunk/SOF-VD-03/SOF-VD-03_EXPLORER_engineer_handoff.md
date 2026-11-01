# Engineer Handoff: SOF-VD-03 EXPLORER

## Issues Resolved

- `QA-001` RESOLVED: Added logical-model shape validation for
  `Select.forEach`, `Select.forEachOrNull`, and `Select.repeat`.
  `repeat` no longer coerces arbitrary iterables such as dicts into path lists.
- `QA-002` RESOLVED: Added boolean validation for `column.collection` and
  direct generator guards for required `Column.path` and collection shape.

## Files Changed

- `fhir4ds/viewdef/types.py`
- `fhir4ds/viewdef/parser.py`
- `fhir4ds/viewdef/generator.py`
- `fhir4ds/viewdef/tests/unit/test_parser.py`
- `fhir4ds/viewdef/tests/unit/test_generator.py`
- `fhir4ds/viewdef/AGENTS.md`

## Validation

- `PYTHONPATH=/mnt/d/fhir4ds python3 .temp/qa/sof_vd_03_explorer_probe.py`
  - Invalid select/column shapes now reject.
  - Multiple root selects, select-relative `forEachOrNull`, and primitive
    `$this` projection still match native C++ and forced Python fallback.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py fhir4ds/viewdef/tests/unit/test_generator.py -q --tb=short`
  - 145 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/viewdef/tests/unit/test_generator.py fhir4ds/viewdef/tests/unit/test_security.py -q --tb=short`
  - 60 passed after preserving the existing invalid identifier error surface.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/viewdef -q --tb=short`
  - 788 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_viewdef.py | grep -E ...`
  - ViewDefinition 134/134 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py | grep -E ...`
  - ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47,
    overall 2822/2822.

## Notes

- No new issues were discovered during remediation.
- The first full ViewDefinition run caught an error-message regression in
  `test_security.py`; the final generator guard keeps existing SQL identifier
  errors stable while validating path/collection shapes earlier.
