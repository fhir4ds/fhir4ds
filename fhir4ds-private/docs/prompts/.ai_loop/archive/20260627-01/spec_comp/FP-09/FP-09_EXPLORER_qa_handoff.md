# QA Handoff - FP-09 EXPLORER

## Scope

Fresh inner-loop QA for SPEC COMPLIANCE CHUNK FP-09: FHIRPath §5.6.1-§5.6.5 String Manipulation (Search):
`indexOf(substring)`, `substring(start, [length])`, `startsWith(prefix)`, `endsWith(suffix)`, and string-function `contains(substring)`.

## Spec Source

Official HL7 FHIRPath continuous-build source:
https://raw.githubusercontent.com/HL7/FHIRPath/refs/heads/master/input/pages/index.md

Relevant normative points verified:
- String operations use Unicode scalar-value character positions, not bytes or grapheme clusters.
- `substring(start[, length])` returns empty when `start` is outside the string.
- `substring(start, length)` returns the empty string `''` when `length` is zero or negative, provided `start` itself is in range.
- `startsWith('')`, `endsWith('')`, and `contains('')` return `true`.
- Empty input returns empty; multi-item input signals an evaluation error to the calling environment.

## Probe

Created `.temp/qa/fp09_explorer_fresh_probe.py`.

The probe compares bundled native DuckDB/C++ registration and forced Python fallback registration over:
- Unicode scalar-value indexing with emoji and combining marks.
- Empty search terms and empty input strings.
- Dynamic sibling-field arguments outside and inside `select()`.
- Multi-item input and multi-item/dynamic wrong-type argument row resilience.
- Negative `substring` length boundaries beyond the existing `start + length <= start` coverage.

## Finding

`QA-001` MEDIUM OPEN: forced Python fallback `substring()` uses Python slicing directly for negative lengths. For sufficiently negative lengths, Python interprets the negative end index relative to the end of the string and returns content instead of the spec-required empty string.

Examples:
- `s.substring(1, -4)` with `s = 'abcdef'`
  - Native: `['']`, text `''`, JSON `[""]`
  - Forced fallback: `['bc']`, text `'bc'`, JSON `["bc"]`
- `s.substring(start, neg)` with `start = 2`, `neg = -4`
  - Native: `['']`, text `''`, JSON `[""]`
  - Forced fallback: `['cd']`, text `'cd'`, JSON `["cd"]`

Reproducer:

```bash
python3 .temp/qa/fp09_explorer_fresh_probe.py
```

## Recommended Fix

In `fhir4ds/fhirpath/engine/invocations/strings.py`, parse and validate `length` before slicing. If `length <= 0`, return `""` after confirming `start` is in range. Add focused parity coverage for `s.substring(1, -4)` and dynamic negative length.
