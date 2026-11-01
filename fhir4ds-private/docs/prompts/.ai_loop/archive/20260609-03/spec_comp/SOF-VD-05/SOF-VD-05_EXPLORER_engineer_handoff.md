# Engineer Handoff - SOF-VD-05 EXPLORER

Issue resolved:
- `SOFVD05-EXPLORER-001` HIGH is `RESOLVED`.

Root cause:
- `Select.to_dict()` serialized direct dataclass `where` values by copying dictionaries directly. That bypassed the shared `validate_where_conditions()` helper used by parser and `SQLGenerator.generate()`, so malformed `where` objects under recursive child selects could be emitted as official SQL-on-FHIR JSON.

Fix:
- Updated `fhir4ds/viewdef/types.py` so `Select.to_dict()` rejects `where=None` and validates/normalizes non-empty `where` values through `validate_where_conditions()`.
- Added focused nested serializer cases in `fhir4ds/viewdef/tests/unit/test_parser.py` for missing `path`, null `description`, and non-string `description` under child `select`.
- Updated `fhir4ds/viewdef/AGENTS.md` with the resolved SOF-VD-05 EXPLORER boundary.

Validation:
- Fresh probe: `python3 .temp/qa/sof_vd05_explorer_probe.py` PASS.
- Focused pytest: 14 passed.
- Full ViewDefinition pytest: 948 passed.
- ViewDefinition conformance: 134/134.
- Full conformance: 2822/2822.

Notes:
- This deliberately fixed the recursive nested `Select.to_dict()` boundary hit by SOF-VD-05. The separate review-45 root `ViewDefinition.where` serialization risk remains outside this chunk unless the outer loop schedules it.
