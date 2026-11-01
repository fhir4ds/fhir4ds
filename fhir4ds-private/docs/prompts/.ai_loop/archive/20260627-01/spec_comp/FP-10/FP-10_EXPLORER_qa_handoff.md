# QA Handoff - FP-10 EXPLORER Unicode i-Flag Retry

Date: 2026-06-12

## Scope

Retry QA for `ARCH-002`: Unicode case-insensitive regex behavior for
`matches(regex, 'i')` and `replaceMatches(regex, substitution, 'i')` in native
DuckDB/C++ versus forced Python fallback.

Spec grounding remains FHIRPath §5.6.9 and §5.6.10: the optional `i` flag
performs case-insensitive search/replacement, and regex functions allow Unicode
characters over strings defined as Unicode scalar values.

## Finding Under Test

`ARCH-002` MEDIUM OPEN: native C++ uses `std::regex_constants::icase`, which
does not provide Unicode case-insensitive matching for UTF-8 non-ASCII
codepoints.

Fresh reproducer added to `.temp/qa/fp10_explorer_fresh_probe.py`:
- `upper_accent.matches('é', 'i')`: native `false`, fallback `true`.
- `upper_accent.matches('[é]', 'i')`: native `false`, fallback `true`.
- `upper_accent.matches('^[é-ë]$', 'i')`: native `false`, fallback `true`.
- Replacement forms with the same literal/class/range patterns are also in the
  probe.

## Validation Run

```bash
python3 .temp/qa/fp10_explorer_fresh_probe.py
```

Result: failed on `upper_accent.matches('é', 'i')`, confirming `ARCH-002`.

## Handoff to Remediation

The native regex adapter should add Unicode case variants when the FHIRPath `i`
flag is present. The fix should cover non-ASCII literal codepoints outside
classes, non-ASCII class members, and expanded Unicode ranges. Preserve the
existing ASCII `icase` behavior, Unicode scalar matching, range handling,
negated classes, multiline anchors, and regex safety guards.
