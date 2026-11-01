# QA Handoff - FP-09 HISTORIAN

Spec source: FHIRPath Normative Release v2.0.0, §4.3 Function Invocations,
§4.4 empty propagation, §4.5 singleton evaluation, and §5.6.1-§5.6.5 string
search functions.

Personality: HISTORIAN. I systematically probed `indexOf(substring)`,
`substring(start, [length])`, `startsWith(prefix)`, `endsWith(suffix)`, and
string-function `contains(substring)` across native C++ DuckDB and forced Python
fallback connections.

Coverage:
- UTF-8 character indexing: emoji and accented characters for `indexOf` and
  `substring`.
- Empty strings and empty collections: empty input, empty search terms, empty
  arguments, and empty optional `length`.
- Bounds: negative start, start at/after string length, overlong length, zero
  length, and negative length.
- Singleton/type behavior: non-string inputs, non-string arguments,
  multi-item inputs, multi-item arguments, invalid arity, and the `contains`
  operator distinct from `contains(...)`.
- Dynamic resource-backed arguments: sibling fields used as search terms,
  prefix/suffix, start, and length.

Finding:
- `QA-001` MEDIUM SPEC_VIOLATION: native C++ evaluated sourced string-search
  arguments against the source string collection rather than the outer focus.
  Reproducer examples: `s.indexOf(term)`, `s.substring(start, length)`,
  `s.startsWith(prefix)`, `s.endsWith(suffix)`, and `s.contains(term)`.
  Native returned empty/NULL while forced Python fallback returned the expected
  value from sibling resource fields.

Probe:
- `.temp/qa/fp09_historian_probe.py` initially reproduced the mismatch.
- After remediation it covered 74 cases with `mismatch_count=0` and
  `failure_count=0`.
