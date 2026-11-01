# QA Handoff - FP-10 SKEPTIC

## Scope

Fresh inner-loop QA for SPEC COMPLIANCE CHUNK FP-10: FHIRPath string transform
functions `upper()`, `lower()`, `replace(pattern, substitution)`,
`matches(regex)`, `replaceMatches(regex, substitution)`, `length()`, and
`toChars()` across native DuckDB/C++ and forced Python fallback paths.

Spec source consulted: official HL7 FHIRPath continuous-build source,
String Manipulation lines covering `matches(regex, [flags])`,
`replaceMatches(regex, substitution, [flags])`, `length()`, and `toChars()`:
https://raw.githubusercontent.com/HL7/FHIRPath/refs/heads/master/input/pages/index.md

## Hypotheses Tested

1. `matches()` may still be implemented as full-string matching instead of
   regex search semantics shown by the official examples.
2. Current optional `i` and `m` flags for `matches()` may not be supported by
   public validators or evaluators.
3. Current optional `i` and `m` flags for `replaceMatches()` may not be
   supported by public validators or evaluators.
4. Invalid flags should remain row-resilient public UDF errors and should make
   `fhirpath_is_valid()` return false.
5. `length()` and `toChars()` should count Unicode scalar values consistently
   across native and fallback paths.

## Findings

### QA-001 - MEDIUM - OPEN

Both native DuckDB/C++ and forced Python fallback are out of date for current
FHIRPath regex transform semantics:

- `url.matches('Library')` returns `false`, but the official examples show
  substring regex search behavior.
- `code.matches('N[0-9]{8}')` returns `false`, but the official examples show
  a regex can match an internal sequence.
- Valid current signatures such as `url.matches('library', 'i')`,
  `line.matches('^second', 'm')`, and `s.replaceMatches('abc', 'X', 'i')`
  return empty/NULL with `fhirpath_is_valid=false`.

Fresh reproducer:

```bash
python3 .temp/qa/fp10_skeptic_fresh_probe.py
```

The probe currently fails on both native and forced Python fallback paths for
the bullets above. It also verifies that Unicode `length()` and `toChars()`
behavior is already aligned for the tested scalar-value cases.

## Files Created

- `.temp/qa/fp10_skeptic_fresh_probe.py`

## Next Phase

Proceed to FIX. Remediation should update the core Python evaluator, public
DuckDB fallback validation, native C++ evaluator/arity validation, focused
parity tests, and native sqllogictest coverage. Rebuild and copy the bundled
extension after native changes.
