# QA Handoff - CQL-12 SKEPTIC

## Scope

Fresh CQL string-operator pass for CQL-12: Combine, Concatenate, EndsWith,
Indexer, LastPositionOf, Length, Lower, Matches, PositionOf, ReplaceMatches,
Split, SplitOnMatches, StartsWith, Substring, and Upper.

## Rehydration

- Read `STATE_SCHEMA.md`, `GLOBAL_RULES.md`, `GLOBAL_KNOWLEDGE.md`,
  `PROC_VALIDATION.md`, root `AGENTS.md`, and `extensions/cql/AGENTS.md`.
- `docs/architecture/translator/AGENTS.md` is not present in this checkout.
- Used the current CQL Reference Appendix B string-operator section as the
  normative source. The relevant signatures are string-only for string
  operators and `List<String>` for `Combine`; explicit conversion is available
  through `ToString`, so silent numeric-to-string coercion is not acceptable.

## Skeptic Hypotheses

1. Direct DuckDB macros may inherit DuckDB implicit casts.
2. Translated CQL may pass statically invalid string operands to SQL instead of
   raising at translation time.
3. Zero-based string indexing may drift at equal-length and negative indexes.
4. Regex helpers may diverge across Python fallback, native-loaded, and
   no-Python runtime on malformed, overlong, or ReDoS patterns.
5. Unicode strings may be handled in bytes rather than characters.

## Probe

Wrote `.temp/qa/cql12_skeptic_probe.py`. Before remediation it confirmed null,
boundary, Unicode, regex, and parity behavior up to the type-discipline checks,
then failed on the first confirmed coercion.

## Finding

`QA-001` HIGH: string operators silently coerce non-string operands.

- `SELECT Concatenate(1, 'x')` returned `'1x'`.
- `SELECT Combine([1, 2])` returned `'12'`.
- Translated CQL definitions `1 & 'x'`, `Concatenate(1, 'x')`, and
  `Combine({1, 2})` produced strings instead of rejecting invalid CQL types.

This violates the CQL string operator signatures and can hide authoring errors
as valid strings.
