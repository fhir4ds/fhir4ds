# Engineer Handoff — SOF-SQ-01 (iteration 1)

All 6 QA issues reproduced and fixed. Files changed (working tree, no commit):
- fhir4ds/fhir4ds/sqlquery/types.py — QA-001/002/006: SQLQUERY/SQLVIEW_PROFILE_CANONICALS frozensets (official hl7.org/fhir/uv + legacy forms), SQLVIEW_LIBRARY_TYPE_CODE="sql-view", to_dict() roundtrip on _SQLLibraryBase, docstring canonicals corrected.
- fhir4ds/fhir4ds/sqlquery/parser.py — QA-001: _matches_canonical against canonical sets (with |version pinning); QA-002: _require_type_coding(data, expected) — sql-query for SQLQuery, sql-view for SQLView; QA-003: base64.b64decode(validate=True); QA-004: parameter.use missing now rejected (1..1).
- fhir4ds/fhir4ds/sqlquery/validator.py — QA-005: SQL_NAME_PATTERN = ^[A-Za-z][A-Za-z0-9_]*$ fullmatch (ASCII); exports updated to canonical-set names.
- fhir4ds/fhir4ds/sqlquery/__init__.py — new exports (canonical sets, SQLVIEW_LIBRARY_TYPE_CODE).
- Tests: tests/test_smoke.py + tests/test_integration.py fixtures updated (SQLView libs now type sql-view); NEW tests/test_sof_sq01_compliance.py (21 focused tests: canonical recognition matrix, version pins, ambiguity, sql-view typing, strict base64 incl. whitespace/non-UTF-8, use cardinality, sql-name invalid/valid labels, to_dict roundtrips).

Validation: sqlquery suite 55/55 passed. Master gate run recorded in architect handoff.

Spec grounding: /mnt/d/sql-on-fhir-v2 branch upstream/sqlquery-view-sources input/fsh/profiles/library-profiles.fsh + terminology.fsh + models.fsh + sushi-config.yaml (canonical http://hl7.org/fhir/uv/sql-on-fhir).

Not-a-bug note: mandate claim "SQLQuery parameter 1..*" contradicts FSH (`parameter MS` only, 0..*); impl 0..* is correct per machine artifact.
