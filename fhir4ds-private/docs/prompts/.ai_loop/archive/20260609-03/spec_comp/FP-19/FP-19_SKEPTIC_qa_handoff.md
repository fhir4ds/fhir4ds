# QA Handoff: FP-19 SKEPTIC

## Scope

FHIRPath §7 Aggregates (STU) and §8 Lexical Elements. Fresh probe:
`.temp/qa/fp19_skeptic_probe.py`.

## Spec Anchors

- §7.1: `aggregate()` initializes `$total` from `init` or empty, then evaluates
  the aggregator for each input item with `$this`, `$index`, and `$total`.
- §8.1: Whitespace is limited to space, tab, line feed, and carriage return.
- §8.5/§8.6 plus formal grammar: keywords are reserved except the identifier
  alternatives `as`, `contains`, `in`, and `is`; other keyword-like fields
  require delimited identifiers.

## Findings

- `QA-001` HIGH: native C++ evaluates aggregate `init` against the aggregate
  input, not the outer focus. Reproducer:
  `a.aggregate($total + $this, seed)` on `{seed:10,a:[1,2,3]}` returns
  empty/NULL in native and `16` in forced Python fallback.
- `QA-002` MEDIUM: native accepts bare `div` and `mod` as field identifiers,
  while fallback rejects them. Delimited `` `div` `` and `` `mod` `` work.
- `QA-003` MEDIUM: native treats actual form-feed and vertical-tab characters
  as whitespace and evaluates `1\f+\f2` / `1\v+\v2` to `3`; fallback rejects
  both and the spec whitespace set does not include those characters.

## Passing Boundaries

Fresh native/fallback probe passed ordinary aggregate sums, no-init aggregate
with `$total.empty()`, `$index` use, `$total` restoration after aggregate,
line/block comments, delimited identifiers with escapes, valid keyword
identifier exceptions (`as`, `is`, `contains`), case-sensitive `TRUE`, and
space/tab/LF whitespace.
