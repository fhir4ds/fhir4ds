# Engineer Handoff — SOF-VD-04 (EXPLORER), iteration 1

## Triage
| Issue | Severity | Category | Disposition |
|---|---|---|---|
| QA-001 whitespace-only tag.name/value rejected | LOW | SPEC_VIOLATION | RESOLVED (surgical) |

## QA-001 fix
- Root cause: `ColumnTag` (fhir4ds/viewdef/types.py) reused
  `validate_required_string`, whose whitespace-stripping doctrine is correct for
  FHIRPath-bearing fields (`column.path`, `where.path`) but overreach for opaque
  tag metadata. Canonical v2 StructureDefinition: `select.column.tag.name`/`.value`
  are plain `string` 1..1 with NO minLength — `' '` is spec-valid.
- Fix: new `validate_tag_string` (non-empty string, whitespace allowed) in
  `fhir4ds/viewdef/types.py`; used at all three `ColumnTag` validation sites
  (`__post_init__`, `from_dict`, `to_dict`). `validate_required_string` docstring
  updated to drop the tag fields from its doctrine scope. Empty string / non-string
  values still rejected (unchanged).
- Regression test: `test_column_tag_whitespace_only_strings_accepted` in
  `fhir4ds/viewdef/tests/unit/test_parser.py` (parse + to_dict round-trip).
- No native/C++ code touched — pure Python layer; extension binary untouched
  (md5 57d0634b6ee6eddee9fc06a1355bef5a, identical across repo bundle and
  site-packages).

## Validation
- ViewDef unit tests: 640/640 passed.
- ViewDefinition conformance suite: 144/144 (100.0%).
- Master gate (run_all.py, final tree): 2832/2832 — see summary log at
  /mnt/d/fhir4ds/.temp/qa/sof_vd04_explorer/validation_summary.log
  (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47; zero FAIL/ERROR lines).
