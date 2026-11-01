# FP-19 QA Handoff — HISTORIAN, iteration 1 (2026-08-18)

Chunk: FHIRPath §7 Aggregates (STU), §8 Lexical Elements.

## Method
Built on the SKEPTIC launch's coverage but hunted NEW divergences. Dual-engine probes
(native fhirpath.duckdb_extension vs Python fallback via fhirpath_scalar, plus
fhirpath_is_valid) from `.temp/qa/fp19h/probe1..3.py`, run with PYTHONPATH=/mnt/d/fhir4ds.
Spec verified against the repo FHIRPath.g4 lexical rules (NUMBER/LONGNUMBER/DATETIME/
TIME/TIMEFORMAT/IDENTIFIER/DELIMITEDIDENTIFIER/STRING/WS/COMMENT/LINE_COMMENT), the
official §7 aggregate dedup example, and FHIR dateTime/time datatype semantics.

## New territory probed (all dual-engine conformant)
- NUMBER lexical boundaries: `.5`, `1.`, `1 .5`, `1e3`, `3.5L` rejected; `007`, `0.0`,
  `1L` accepted (grammar: leading zeros allowed, LONGNUMBER = integer + 'L', no space).
- DATETIME/TIME literals: `@2018`, `@2018-02`, `@2018-02-04T`, offset forms,
  `@T12`, `@T12:30` fine; `@2018-1` rejected (strict digit counts); `@2018-13`,
  `@2018-02-30`, `@T12:30:61` eval-empty both engines.
- QUANTITY literals: `10 'mg'`, `4.5 'wk'`, `10 'cm/mmol'` all parse with `.value`
  and `.unit` extracted; UCUM equality `10 'cm' = 100 'mm'` → true.
- Comment lexer ordering: `'http://not-a-comment'` and `'/* not comment */'` NOT
  stripped; `1//c\n+2`, `1/*c*/+2`, multi-line block comments fine.
- Case sensitivity: `DIV`/`Div`/`MOD`/`IN` rejected, lowercase works. Non-ASCII
  identifiers (`café`) rejected per grammar charset. Empty/backtick-space identifiers
  accepted (grammar-permitted, eval empty). Whitespace around `.` navigation tolerated.
- §7 aggregate composition: `$index` inside aggregator is the 0-based current-item
  index (`a.aggregate($this+$total+$index,0)` = 63 for [10,20,30]); init evaluated
  once and may reference outer context (`a.aggregate($this+$total, a.count())` = 63);
  chained (`...aggregate(...).abs()`) and nested aggregates correct; official §7 dedup
  example `iif($total contains $this, $total, $this | $total)` returns [3,2,1] both
  engines; `$total` referenced in init → empty in both (undefined corner, parity).
  No `sum()` function exists in FHIRPath — `$total.sum()` correctly warned+empty.
- `@2018Z` and `@T12:30Z` rejected in both engines: grammar permits 'Z' lexically but
  FHIR datetime semantics disallow timezone without time components / on time-only
  values; matches documented FP-06/CQL-11 strictness decisions.

## Issues
- QA-001 LOW INTENDED: `@2018Z`/`@T12:30Z` rejection is documented strictness
  (grammar-lenient vs FHIR-datatype-strict corner); dual-engine parity holds.
- QA-002 LOW INTENDED: verification-only pin of HISTORIAN extension coverage (above);
  no divergence found on any probe.

## Conclusion
Zero CRITICAL/HIGH/MEDIUM non-terminal issues → clean exit eligible at
min_iterations=1. Conformance baseline re-check running; see engineer/architect
handoffs for final numbers.
