# QA Handoff: CQL-12 HISTORIAN

## Scope

Spec compliance chunk CQL-12, CQL string operators: Combine, Concatenate,
EndsWith, Indexer, LastPositionOf, Length, Lower, Matches, PositionOf,
ReplaceMatches, Split, SplitOnMatches, StartsWith, Substring, and Upper.

Official reference checked: CQL Reference v1.5.3 Appendix B, String Operators.
Key boundaries tested: exact signatures, null propagation, 0-based string
indexes, out-of-range behavior, regex partial/single-line mode, replacement
capture/literal-dollar behavior, Unicode character indexing, and the CQL-12
SKEPTIC non-string coercion guardrail.

## Fresh Probe

Created `.temp/qa/cql12_historian_probe.py`.

The probe exercises:
- Parser coverage for all CQL-12 function forms plus string `[]`.
- Translated CQL execution on forced Python fallback and native-loaded
  registrations.
- Direct public DuckDB helper/macro calls on forced Python fallback,
  native-loaded registration, and no-Python C++/macro runtime.
- Invalid direct non-string inputs for `Concatenate`, `Combine`, and
  `CombineSep` on the no-Python runtime.

## Findings

`QA-001` HIGH: direct public DuckDB `Substring` lacks the official
three-argument overload.

Evidence:
- `SELECT Substring('😀x', 0, 1)` raises a DuckDB `BinderException`.
- `SELECT Substring('abc', 1, CAST(NULL AS INTEGER))` raises the same binder
  error instead of returning SQL `NULL`.
- `SELECT Substring('abc', 1, -1)` raises the same binder error instead of
  returning SQL `NULL`.
- The failure reproduces on forced Python fallback, native-loaded registration,
  and no-Python C++/macro runtime.
- Translated CQL already handles `Substring('😀x', 0, 1)` correctly, so this is
  a direct public helper surface gap rather than a parser/translator failure.

## Expected Fix

Register direct `Substring` with an optional length parameter while preserving:
- Existing two-argument behavior.
- Existing `SubstringLen` compatibility alias.
- SQL `NULL` for explicit null length and negative length.
- SQL `NULL` for null/negative/at-or-past-end starts.
- UTF-8 character-count behavior inherited from DuckDB string functions.
