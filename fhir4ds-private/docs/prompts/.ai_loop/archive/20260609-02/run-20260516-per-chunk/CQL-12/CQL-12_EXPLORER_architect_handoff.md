# Architect Handoff - CQL-12 EXPLORER

Verdict: PASS.

The CQL-12 EXPLORER pass found four additional public-surface defects and
resolved them without open issues. The final CQL-12 chunk status is pass after
all three personalities.

Architectural guardrails established:
- `CombineSep` null separators are CQL empty separators, not DuckDB comma
  defaults.
- CQL string indexer classification must include derived string-producing
  functions, not only string literals and direct casts.
- `&` and `Concatenate` are distinct operators: `&` treats null as empty,
  while `Concatenate` returns null when either argument is null.
- Regex-backed string operators are public compatibility surface in translated
  CQL, forced Python fallback, native-loaded DuckDB, and no-Python/browser-style
  direct SQL. Keep Python and native C++ `cqlRegex*` helpers aligned when
  extending regex behavior.
- New regex paths must pass through the shared ReDoS guard before compilation.

Validation reviewed:
- Focused string parity pytest passed.
- Focused string plus WASM/C++-surface pytest bundle passed.
- Native C++ CQL unittest passed 672 assertions.
- Official CQL conformance passed 1706/1706.
- Full conformance passed 2822/2822.
- Full repository pytest passed 7179 with 5 skips and 9 warnings.
- Native and bundled CQL extension SHA-256 matched.

No milestone review is due after CQL-12 because completed chunk count is 32 and
the workflow review cadence is every 5 completed chunks.
