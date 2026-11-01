# Engineer Handoff - FP-09 EXPLORER

## Triage

| Issue | Severity | Category | Status |
|---|---:|---|---|
| `QA-001` | MEDIUM | SPEC_VIOLATION | RESOLVED |

## Root Cause

Forced Python fallback `fhirpath_is_valid()` used a masked-token literal-union precheck for FP-09 string-search arguments. That shortcut could see that a `|` was present, but not the effective union collection after duplicate elimination. As a result, it falsely rejected `s.indexOf(('a'|'a'))` and failed to reject multi-item Integer unions in `substring` arguments.

## Fix

- Updated `fhir4ds/fhirpath/duckdb/udf.py` with position-preserving function-call scanning for FP-09 validation.
- Added parsing for simple literal union arguments, including empty collection, String, Boolean, Integer, Decimal, and temporal literal shapes.
- Applied FHIRPath union duplicate elimination before checking FP-09 singleton parameter cardinality and type, including numeric equality while preserving the first effective item type.
- Removed the older blanket string-literal union rejection from the masked-token path.
- Added regression coverage in `test_string_search_parity.py` for duplicate and multi-item literal-union arguments on both native and forced fallback connections.

## Spec Reference

- FHIRPath Normative Release section 4.5: singleton arguments with multiple items signal an error.
- Section 5.6.1: `indexOf(substring : String)` uses a singleton String substring.
- Section 5.6.2: `substring(start : Integer [, length : Integer])` uses singleton Integer start/length arguments.
- Section 6.4.1: union eliminates duplicate values.

## Validation

- `.temp/qa/fp09_explorer_probe.py`: 43 cases, 0 native/fallback mismatches, 0 expectation failures.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_string_search_parity.py -q`: 6 passed.
- `python3 conformance/scripts/run_all.py | grep ...`: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## New Issues

None.
