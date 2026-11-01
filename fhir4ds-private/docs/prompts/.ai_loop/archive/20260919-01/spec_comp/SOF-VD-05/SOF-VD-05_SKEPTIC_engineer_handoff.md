# Engineer Handoff — SOF-VD-05 (iteration 1, 2026-08-23)

## Triage table
| Issue | Category | Severity | Action |
|---|---|---|---|
| QA-001 | SPEC_VIOLATION | MEDIUM | CONFIRMED → fixed |
| QA-002 | SPEC_VIOLATION | MEDIUM | CONFIRMED → fixed |
| QA-003 | SPEC_OBSERVATION | LOW | INTENDED (documented) |

## Fixes
Both fixes are one surgical change in `fhir4ds/viewdef/parser.py::_parse_select`:

1. **QA-001** (unknown select fields): added an unknown-field check mirroring the
   existing `_parse_column` rejection (parser.py:141 precedent). Spec: official
   validator `sof-js/src/validate.js` select items are `additionalProperties:false`;
   allowed set = column, select, unionAll, forEach, forEachOrNull, repeat (+ where,
   retained per established fhir4ds select-level-where doctrine, SOF-VD-09).
   Typed ParseError names the offending fields and the allowed set.
2. **QA-002** (present-empty arrays): `column` and nested `select` now parsed with
   `require_non_empty=True` (same helper already used for `unionAll`; `repeat` had
   its own guard from SOF-VD-07). Spec: validator `minItems: 1` on both arrays.

Regression tests: `fhir4ds/viewdef/tests/unit/test_parser.py::
TestSelectUnknownFieldAndEmptyContainerRejectionPerSpecSofVd05Skeptic` (6 tests:
contentReference, columns typo, depth-2 unknown field, empty column array, empty
nested select array, valid nested baseline still accepted + generates SQL).

## Verification (FINAL tree, PYTHONPATH=/mnt/d/fhir4ds)
- Focused: test_parser.py 322/322.
- ViewDefinition pytest: 1185/1185.
- Conformance: ViewDefinition 144/144; master gate 2832/2832
  (FHIRPath 935/935, CQL 1706/1706, DQM 47/47). No regressions.
- Binary md5s (unchanged this launch — no native code touched):
  - cql.duckdb_extension c5b22d58310c1eb7bafa17ce7877f989 (repo bundle ==
    ~/.local site-packages)
  - fhirpath.duckdb_extension 57d0634b6ee6eddee9fc06a1355bef5a (repo bundle ==
    site-packages == build/release)

## New issues discovered
None beyond QA-003 (documented as INTENDED).
