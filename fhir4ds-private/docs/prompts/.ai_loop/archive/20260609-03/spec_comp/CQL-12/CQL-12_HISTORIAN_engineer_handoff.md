# Engineer Handoff: CQL-12 HISTORIAN

## Triage

| Issue | Severity | Category | Status |
| --- | --- | --- | --- |
| QA-001 | HIGH | SPEC_VIOLATION | RESOLVED |

## Fix

`QA-001`: Direct public DuckDB `Substring` did not expose the official
three-argument CQL overload. `registerStringMacros` registered
`Substring(s, start)` and separately registered the non-spec compatibility
alias `SubstringLen(s, start, len)`, so direct calls such as
`Substring('abc', 1, 2)` failed at bind time.

Changed `fhir4ds/cql/duckdb/macros/string.py` so:
- `Substring(s, start, len := -2147483649)` supports omitted and explicit
  length in one macro.
- Omitted length preserves the existing "substring to end" behavior.
- Explicit `NULL` or negative length returns SQL `NULL`.
- `SubstringLen(s, start, len)` remains as a compatibility alias.

## Tests Added

- Extended `fhir4ds/cql/duckdb/tests/integration/test_string_operator_parity.py`
  with direct three-argument `Substring` coverage across forced Python fallback,
  native-loaded, and no-Python/browser-style runtime paths.
- Extended `fhir4ds/cql/duckdb/tests/test_macros_tier1.py` to exercise direct
  `Substring('hello', 1, 3)`, `SubstringLen` compatibility, and explicit null
  length.
- Added fresh probe `.temp/qa/cql12_historian_probe.py`.

## Validation

- Fresh probe: PASS.
- Focused string parity/macros pytest: 74/74.
- Official CQL string parser subset: 81/81.
- Official CQL string execution subset: 81/81.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.

## Files Changed

- `fhir4ds/cql/duckdb/macros/string.py`
- `fhir4ds/cql/duckdb/tests/integration/test_string_operator_parity.py`
- `fhir4ds/cql/duckdb/tests/test_macros_tier1.py`
- `extensions/cql/AGENTS.md`
- `.temp/qa/cql12_historian_probe.py`
