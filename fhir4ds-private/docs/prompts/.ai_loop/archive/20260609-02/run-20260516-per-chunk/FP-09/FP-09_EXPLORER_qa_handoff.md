# QA Handoff - FP-09 EXPLORER

## Scope

FHIRPath N1 §5.6.1-§5.6.5 string search functions:
`indexOf(substring)`, `substring(start, [length])`, `startsWith(prefix)`,
`endsWith(suffix)`, and `contains(substring)`.

## Spec Basis

Verified against HL7 FHIRPath Normative Release v2.0.0 §5.6. The relevant
rules are:

- String manipulation functions operate on singleton String input; multiple
  items or non-String input signal an error to the caller.
- `indexOf('')` returns `0`; missing substrings return `-1`.
- `startsWith('')`, `endsWith('')`, and `contains('')` return `true`.
- Empty input or empty argument collections return empty.
- `substring()` is zero-based; starts outside the string return empty; provided
  length bounds the returned characters.

## Exploration

Created `.temp/qa/fp09_explorer_matrix.json` with a native C++ DuckDB vs forced
Python fallback matrix across 32 expressions, including:

- Empty substring arguments.
- Unicode code-point positions (`é`, `𝄞`).
- `substring()` start-at-length, zero-length, negative-length, and empty-length
  argument cases.
- Multi-item, numeric, boolean, object, and null inputs.
- Non-string and non-integer argument cases.

Also created `.temp/qa/fp09_direct_helpers.json` to probe exported direct helper
functions in `fhir4ds.fhirpath.duckdb.functions.string`.

## Findings

No CRITICAL/HIGH/MEDIUM spec issues found.

Public DuckDB UDF behavior matched between native C++ and forced Python fallback
for every tested expression. Invalid public-UDF cases returned the same
row-resilient empty/NULL outputs on both paths.

Observation: direct helper calls with invalid search arguments raise raw Python
`TypeError` for `starts_with(..., 1)`, `ends_with(..., 1)`, and
`contains(..., 1)`. This is not logged as a spec failure because it still
signals an error to the calling environment and the public SQL UDF surface is
already consistent. It is a possible future hardening cleanup if the helper API
is expected to normalize all invalid argument errors to `FHIRPathFunctionError`.

## Validation

- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_string_search_parity.py fhir4ds/fhirpath/duckdb/tests/unit/test_string.py -q`
  - Result: 97 passed.

## Issues

None.
