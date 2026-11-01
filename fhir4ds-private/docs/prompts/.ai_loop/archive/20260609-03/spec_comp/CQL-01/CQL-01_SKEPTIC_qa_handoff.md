# QA Handoff - CQL-01 SKEPTIC

Scope: CQL primitive types, with emphasis on `System.Any`, Boolean-only logic boundaries, Integer/Long range limits, Decimal precision preservation, String escapes, primitive `is`/`as`, invalid numeric suffixes, and DuckDB native vs forced Python fallback parity.

Spec sources checked:
- CQL 1.5.3 Developer Guide §1.3 Literals: primitive literal categories and string escape table.
- CQL 1.5.3 Appendix L syntax diagrams: `STRING`, `ESC`, and `LONGNUMBER` grammar.

Probe written:
- `.temp/qa/cql01_skeptic_probe.py`

Hypotheses exercised:
- `System.Any` should behave as the maximal primitive supertype at translator boundaries.
- Boolean, Integer, Long, Decimal, and String public helper surfaces should match between native-loaded and forced Python fallback DuckDB registrations.
- Integer and Long signed minima must be accepted only through unary negation and out-of-range literals must fail.
- Decimal precision should preserve authored fractional scale for `Precision()`.
- CQL string escapes should decode every spec-listed escape and not leave encoded spellings in runtime strings.
- Invalid numeric suffixes should be rejected, including lowercase `l` after an integer.

Findings:
- `QA-001` MEDIUM: CQL string escapes for `\/` and ``\` `` are not decoded. Probe observed `'a\/b'` executing as `a\/b` and `'a\`b'` executing as `a\`b`, while the spec escape table lists slash and backtick escapes.
- `QA-002` MEDIUM: The lexer accepts lowercase `l` as a Long suffix. Probe observed `define X: 1l` tokenizing as `LONG`, while Appendix L defines `LONGNUMBER` with uppercase `L`.

Other checked boundaries matched expectations:
- `5 is Any`, `5 is System.Any`, `null is Any`, primitive `as`, Integer/Long min/max, Decimal `Precision(1.2300)`, and direct `ToInteger`/`ToLong`/`ToDecimal`/`ToBoolean` helper parity matched expected native and forced fallback behavior.
