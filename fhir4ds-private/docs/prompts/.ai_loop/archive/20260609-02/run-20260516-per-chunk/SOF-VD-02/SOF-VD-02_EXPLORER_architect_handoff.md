# Architect Handoff - SOF-VD-02 EXPLORER

## Structural Health

The SOF-VD-02 EXPLORER remediation is structurally sound. Constant
responsibilities are now correctly layered: `types.py` validates primitive
`value[x]` shape and FHIR JSON representation, `constants.py` owns FHIRPath
constant lexical scanning and literal serialization, and `generator.py` consumes
that shared scanner for undefined-reference validation before SQL generation.
No new architecture issues were found.

## Issue Summary

- `QA-001` HIGH: verified fixed. Regex-only constant handling was replaced by a
  shared FHIRPath lexical scanner, and string constants now become FHIRPath
  literals before SQL escaping.
- `QA-002` MEDIUM: verified fixed. `valueInteger64` now follows FHIR JSON
  string representation rules and still resolves to a numeric FHIRPath literal.

## QA Audit

QA was not lazy. The EXPLORER pass covered parser validation, SQL generation,
DuckDB execution, official constants fixtures, and native C++ versus forced
Python fallback parity. It found edge cases not present in the official
fixtures: `%name` text inside string literals, apostrophes in string constants,
and integer64 JSON encoding. No `RETRY_QA` flag is needed.

## Verification Reviewed

- Focused unit/generator tests: 147 passed
- Native/fallback ViewDefinition integration test: 1 passed
- ViewDefinition tests: 743 passed
- ViewDefinition conformance: 134/134
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822
- Full package pytest: 7280 passed, 5 skipped

## Recommended Fix Order

No follow-up fixes are required for this chunk. Future work should avoid adding
alternate constant scanners or value-field parsing in generator code; extend the
central `constants.py` scanner if SQL-on-FHIR later supports quoted FHIRPath
external constant names.
