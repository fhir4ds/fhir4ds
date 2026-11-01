# QA Handoff - FP-10 HISTORIAN

Date: 2026-06-12

## Scope

SPEC COMPLIANCE CHUNK FP-10, FHIRPath §5.6.6-§5.6.12 String Manipulation
(Transform): `upper()`, `lower()`, `replace(pattern, substitution)`,
`matches(regex, [flags])`, `replaceMatches(regex, substitution, [flags])`,
`length()`, and `toChars()`.

Personality: HISTORIAN.

## Spec Basis

Official source checked: HL7 FHIRPath continuous-build source,
`input/pages/index.md`, §5.6.6-§5.6.12.

Normative behavior used for testing:
- `upper()` and `lower()` convert all characters in a singleton input string
  to upper or lower case; empty input returns empty; multi-item input signals
  an error.
- `replace()` replaces all literal pattern instances; an empty pattern
  surrounds every Unicode scalar-value character with the substitution.
- `matches()` uses regex search semantics, accepts optional `i` and `m` flags,
  and invalid flags signal an error.
- `replaceMatches()` applies regex replacement with the same optional flags.
- `length()` and `toChars()` count/split Unicode scalar values, not bytes or
  grapheme clusters.

## Hypotheses Tested

1. Native and fallback regex behavior stayed aligned after FP-10 SKEPTIC.
2. Empty-pattern `replace()` preserves Unicode scalar values such as emoji.
3. `length()` and `toChars()` count/split Unicode scalar values for combining
   and non-BMP characters.
4. Dynamic sibling arguments for `replace()`, `matches()`, and
   `replaceMatches()` still evaluate against the outer invocation focus.
5. Native `upper()`/`lower()` may be incomplete because its implementation uses
   hand-written case maps rather than Unicode-wide case data.

## Findings

`QA-001` MEDIUM OPEN: Native DuckDB/C++ `upper()` and `lower()` do not convert
all Unicode characters to case as required by §5.6.6/§5.6.7. Forced Python
fallback uses Unicode case conversion and returns expected results.

Fresh reproducer:

```bash
python3 .temp/qa/fp10_historian_fresh_probe.py
```

Failure before remediation:

```text
native mismatch for eszett_cap.lower():
(['ẞ'], 'ẞ', '["ẞ"]', None, None, True)
!= (['ß'], 'ß', '["ß"]', None, None, True)
```

Additional native mismatches in the same probe:
- `ligature.upper()` returned `ﬃ` instead of `FFI`.
- `deseret_lower.upper()` returned `𐐨` instead of `𐐀`.
- `armenian_lower.upper()` returned `ա` instead of `Ա`.
- `georgian_lower.upper()` returned `ა` instead of `Ა`.
- `latin_ext_b_lower.upper()` returned `ƀ` instead of `Ƀ`.

## Files Produced

- `.temp/qa/fp10_historian_fresh_probe.py`
- `fhir4ds-private/docs/prompts/.ai_loop/evolution.json`

## Recommended Fix

Replace or extend the native C++ `fn_upper()` / `fn_lower()` hand-written case
mapping so it uses a broader Unicode case map, including one-to-one mappings
outside Latin/Greek/Cyrillic and full-case expansions such as `ﬃ` -> `FFI`.
Add these fresh cases to `test_string_transform_parity.py` and native SQL test
coverage, rebuild/copy the bundled extension, then rerun the fresh probe and
focused parity validation.
