# Engineer Handoff — SOF-VD-09 SKEPTIC (2026-08-23, iteration 1)

Triage: QA-001 MEDIUM SPEC_VIOLATION — CONFIRMED (reproduced via probe H11 +
validator schema comparison).

Root cause: `fhir4ds/viewdef/parser.py:_parse_where` delegated wholly to the
permissive convenience validator `validate_where_conditions` (accepts
str/dict/list-of-str, preserves unknown keys), so the strict official-JSON
boundary never enforced the official validator schema for
`ViewDefinition.where` (array of objects, required path,
additionalProperties:false, FHIR repeating-elements-are-arrays rule).

Fix (surgical, at the parser boundary only):
- `_parse_where` now rejects non-array where, non-object items, and unknown
  item fields (allowed: path, description) with typed ParseError.
- `validate_where_conditions` (types.py) intentionally unchanged — it remains
  the permissive normalization boundary for direct dataclass /
  serializer (`to_dict`) inputs, preserving the established strict-parser vs
  permissive-dataclass split (SOF-VD-10 doctrine).
- Generator `_validate_where_shapes` untouched (direct-dataclass boundary).

Tests:
- Updated 3 tests that encoded the string shorthand as expected behavior:
  test_parser.py::test_select_with_string_where (now asserts rejection),
  test_parser.py::test_view_definition_with_string_where (now asserts
  rejection), test_parser.py::TestSelectParsing::test_view_definition_from_dict_reuses_root_parser_validation
  (dict-where now asserted rejected; valid array form added),
  test_duckdb.py (string where -> array form).
- New regression class
  `TestWhereOfficialJsonShapePerSpecSofVd09Skeptic` (7 tests incl.
  parametrized unknown-field cases) in tests/unit/test_parser.py.

Validation (final tree, PYTHONPATH=/mnt/d/fhir4ds):
- viewdef pytest: 1216/1216
- ViewDefinition conformance: 144/144 (where.json 8/8)
- Master gate: 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47)
- Probe post-fix: 32/32 native AND forced fallback
- Binary md5 57d0634b6ee6eddee9fc06a1355bef5a identical across repo bundle
  and ~/.local site-packages (no native changes made this launch).

Status: QA-001 RESOLVED -> VERIFIED (reproducer inverted to rejection +
regression tests + baseline holds).
