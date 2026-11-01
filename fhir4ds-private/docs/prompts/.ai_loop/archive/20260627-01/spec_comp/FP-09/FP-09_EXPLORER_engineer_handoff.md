# Engineer Handoff - FP-09 EXPLORER

## Issue Summary

Resolved `QA-001` (MEDIUM, SPEC_VIOLATION): forced Python fallback `substring(start, length)` returned content for sufficiently negative `length` values due to Python negative slice-end semantics.

## Spec Reference

Official HL7 FHIRPath §5.6.2 `substring(start : Integer [, length : Integer]) : String`:
- `start` and `length` are measured in Unicode scalar-value characters.
- If `start` is outside or equal to the string length, the result is empty (`{ }`).
- If `length` is empty, behavior is the same as omitting it.
- If `length` is negative or zero, the result is the empty string (`''`).

## Root Cause

`fhir4ds/fhirpath/engine/invocations/strings.py::substring` validated `start` but then returned:

```python
string[start : start + int(length)]
```

When `start + length` was negative, Python treated the end index relative to the end of the string. For example, `abcdef[1:-3]` produced `bc`, violating FHIRPath's `length <= 0` rule.

## Fix

Changed Python fallback `substring()` to:
- Preserve existing empty input/start and out-of-range `start` behavior.
- Preserve omitted/empty `length` behavior.
- Convert `length` once and return `""` whenever `length <= 0`.
- Slice only when `length > 0`.

Added focused native/fallback parity coverage in `test_string_search_parity.py` for:
- `s.substring(1, -4)`
- dynamic `s.substring(1, negLen)`

## Files Changed

- `fhir4ds/fhirpath/engine/invocations/strings.py`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_string_search_parity.py`
- `.temp/qa/fp09_explorer_fresh_probe.py`
- `fhir4ds/fhirpath/AGENTS.md`
- `extensions/fhirpath/AGENTS.md`
- `.ai_loop` state and handoff files

## Validation

```bash
python3 .temp/qa/fp09_explorer_fresh_probe.py
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_string_search_parity.py -q
git diff --check -- fhir4ds/fhirpath/engine/invocations/strings.py fhir4ds/fhirpath/duckdb/tests/integration/test_string_search_parity.py fhir4ds/fhirpath/AGENTS.md extensions/fhirpath/AGENTS.md fhir4ds-private/docs/prompts/.ai_loop .temp/qa/fp09_explorer_fresh_probe.py
python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"
```

Results:
- Fresh probe passed, 46 expressions.
- Focused pytest passed, 6/6.
- Diff whitespace check passed.
- Full conformance passed: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## New Issues

None.
