# Engineer Handoff: SOF-VD-09 / SKEPTIC

## Issue Addressed

`SOFVD09-SKEPTIC-001` HIGH: root `ViewDefinition.to_dict()` could emit
invalid official JSON for malformed root `where` entries, even though parser
and SQL generator preflight rejected the same shapes.

## Root Cause

`Select.to_dict()` already normalized nested `where` through
`validate_where_conditions()`, and `SQLGenerator.generate()` did the same for
direct dataclass execution. Root `ViewDefinition.to_dict()` instead copied
`self.where` entries verbatim, so direct dataclass serializers could output
entries without required `path` or with invalid/null `description`.

## Fix

Updated `ViewDefinition.to_dict()` in `fhir4ds/viewdef/types.py` to:

- reject `ViewDefinition.where=None`;
- validate and normalize non-empty root `where` through
  `validate_where_conditions()`;
- preserve valid root `where.description` values.

Added regression tests in
`fhir4ds/viewdef/tests/unit/test_parser.py` for valid description retention and
malformed root `where` serializer inputs.

Updated the fresh probe at `.temp/qa/sof_vd09_skeptic_probe.py`; it now
prepends the repo root to `sys.path` so it cannot import an installed/stale
package when run from `.temp/qa`.

## Validation

- Fresh probe: `PASS: SOF-VD-09 root where probe`
- Focused pytest:
  `python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py fhir4ds/viewdef/tests/unit/test_where.py fhir4ds/viewdef/tests/integration/test_duckdb.py -q`
  -> `285 passed`
- Full ViewDefinition pytest:
  `python3 -m pytest fhir4ds/viewdef/tests -q` -> `960 passed`
- ViewDefinition conformance: `134/134`
- Full conformance: `2822/2822`

## New Issues

None.
