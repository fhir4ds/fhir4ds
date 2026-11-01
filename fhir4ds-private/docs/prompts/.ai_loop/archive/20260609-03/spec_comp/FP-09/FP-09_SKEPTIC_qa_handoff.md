# QA Handoff — FP-09 SKEPTIC

## Scope

- Chunk: FP-09, FHIRPath Normative Release §5.6.1-§5.6.5.
- Personality: SKEPTIC.
- Functions probed: `indexOf(substring)`, `substring(start, [length])`, `startsWith(prefix)`, `endsWith(suffix)`, `contains(substring)`.
- Backends compared: DuckDB native C++ extension and forced Python fallback in isolated subprocesses.

## Spec Grounding

Verified directly against https://hl7.org/fhirpath/N1/:

- §5.6 functions operate on singleton String input; multiple input items or a non-String item must signal an error to the calling environment.
- §5.6.1 `indexOf(substring : String)` returns a 0-based index, `-1` when missing, `0` for empty string search, and empty when input or substring is `{}`.
- §5.6.2 `substring(start : Integer [, length : Integer])` returns codepoint-positioned substrings, empty for outside start, empty when input or start is `{}`, and treats empty `length` like omitted.
- §5.6.3-§5.6.5 `startsWith`, `endsWith`, and string-function `.contains()` return true for empty search text and empty when input is `{}`.

## SKEPTIC Hypotheses Tested

1. Native string-search dispatch may still lack exact arity checks, matching prior FP-05/FP-08 bug patterns.
2. Native type mismatches may return empty instead of semantic errors, causing `fhirpath_is_valid()` drift.
3. UTF-8 codepoint indexing may differ from byte indexing for `indexOf()` and `substring()`.
4. Empty search text may be conflated with empty collection.
5. Empty optional `substring` length may be treated as invalid instead of omitted.

## Probe

- Probe script: `.temp/qa/fp09_skeptic_probe.py`
- Log: `.temp/qa/fp09_skeptic_probe.log`
- Cases: 32
- Native extension loaded: true
- Forced fallback loaded native extension: false

Controls passed for both backends:

- UTF-8 codepoint behavior: `s.indexOf('😊') = 2`, `s.substring(1, 2) = 'é😊'`.
- Empty search text: `indexOf('') = 0`, `startsWith('')`, `endsWith('')`, and `contains('')` are true.
- Empty propagation: `{}.contains('x')` and `ascii.indexOf({})` return empty/NULL.
- `substring(3, {})` behaves like `substring(3)`.

## Findings

### QA-001 HIGH — Native exact arity is not enforced

Native C++ ignores extra arguments and reports malformed arity as valid:

- `'abc'.indexOf('a','b')` returns `['0']`, text `0`, number `0.0`, json `[0]`, `is_valid=true`.
- `'abc'.substring(1,2,3)` returns `['bc']`, `is_valid=true`.
- `'abc'.startsWith('a','b')`, `'abc'.endsWith('c','b')`, and `'abc'.contains('b','c')` return `true`, `is_valid=true`.
- Missing argument forms such as `'abc'.indexOf()` and `'abc'.substring()` also report `is_valid=true`.

Forced Python fallback returns empty/NULL and `is_valid=false` for these malformed calls.

### QA-002 MEDIUM — Native constant wrong-type validation is too permissive

Native C++ returns empty but `fhirpath_is_valid=true` for constant wrong-type calls:

- `'abc'.contains(1)`
- `'abc'.startsWith(1)`
- `1.indexOf('1')`
- `1.contains('1')`
- `'abc'.substring('1')`
- `'abc'.substring(1.5)`
- `'abc'.substring(1,'2')`

Forced Python fallback returns empty/NULL and `is_valid=false`.

## Recommended Fix

- Add exact native arity guards for `indexOf`, `substring`, `startsWith`, `endsWith`, and string-function `contains` before evaluating `node.children[0]`.
- For these §5.6 functions, throw `FHIRPathSpecError` on non-String input/argument and non-Integer substring parameters instead of returning empty for concrete wrong-type values.
- Preserve valid empty propagation: empty input, empty argument, and empty `substring` length must still return empty or omitted-length behavior as specified.
