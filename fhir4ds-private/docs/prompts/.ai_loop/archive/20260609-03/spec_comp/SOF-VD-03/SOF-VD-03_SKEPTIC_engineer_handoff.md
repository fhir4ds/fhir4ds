# Engineer Handoff - SOF-VD-03 SKEPTIC

## Issue Resolved

`SOF-VD03-SKEPTIC-001` (HIGH) is `RESOLVED`.

Root cause: parser and `ViewDefinition.from_dict()` enforced SOF-VD-03
select/column shape rules, but direct dataclass boundaries did not. In
particular, `SQLGenerator.generate()` accepted an empty root `select`, and
`ViewDefinition.to_dict()` / nested serializers could emit invalid official JSON
for direct `Column` and `Select` objects.

## Fix

- `SQLGenerator.generate()` now rejects direct `ViewDefinition.select=[]` with
  `ValidationError`.
- `Column.to_dict()` now validates required `path`, required sql-name `name`,
  markdown `description`, Boolean `collection`, type shape, and tag container
  shape before emitting official JSON.
- `Select.to_dict()` now validates direct container and iterator shapes before
  serializing nested `column`, `select`, and `unionAll` structures.
- `ViewDefinition.to_dict()` now enforces root `select` as a non-empty array of
  `Select` objects.

## Tests Added

- Direct serializer validation tests in
  `fhir4ds/viewdef/tests/unit/test_parser.py`.
- Direct generator root-select cardinality test in
  `fhir4ds/viewdef/tests/unit/test_generator.py`.
- Fresh probe:
  `.temp/qa/sof_vd03_skeptic_probe.py`.

## Validation

- `python3 .temp/qa/sof_vd03_skeptic_probe.py` - PASS
- `python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py fhir4ds/viewdef/tests/unit/test_generator.py -q` - 242 passed
- `python3 -m pytest fhir4ds/viewdef/tests -q` - 940 passed
- `python3 conformance/scripts/run_viewdef.py` - 134/134
- `python3 conformance/scripts/run_all.py` - overall 2822/2822

No new issues were discovered during remediation.
