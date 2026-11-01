# FP-19 QA Handoff — SKEPTIC, iteration 1 (2026-08-18)

Chunk: FHIRPath §7 Aggregates, §8 Lexical Elements.

## Method
Dual-engine probes (native fhirpath.duckdb_extension vs Python fallback, full UDF
surface: fhirpath/fhirpath_text/fhirpath_json/fhirpath_bool/fhirpath_number +
fhirpath_is_valid) from `.temp/qa/probe1..4.py`. Spec verified against repo
FHIRPath.g4 lexical rules, official R4 fixture tests-fhir-r4.xml (testAggregate1-4,
lines 554-557), and FHIRPath spec pages.

## Verified conformant (no issues)
- aggregate two-arg: init as $total start, aggregator over $total/$this (45/47 fixtures reproduced live).
- aggregate one-arg: $total starts EMPTY — `(1|2|3).aggregate($this+$total)` → empty is CORRECT per fixture-canonical `iif($total.empty(),...)` pattern. Empty input + init → init; empty input no init → empty.
- Collection init `aggregate($total.union($this), {})` builds collections correctly in both engines.
- $total/$this/$index scoping saved/restored; nested select/aggregate rebinding and post-aggregate scope restoration correct (matches existing test_aggregate_scope_restoration).
- iif laziness: `iif(true,1,1/0)`→1, `iif(false,1/0,2)`→2, `iif({},1/0,3)`→3 both engines; lazy iif inside aggregator works.
- Comments: `//` line, `/* */` block (non-nested → syntax error on nesting attempt, correct per non-greedy grammar), unterminated block → syntax error. Whitespace/tabs/newlines mid-expression all tolerated.
- Literals: full escape set \' \\ \/ \f \n \r \t A correct in both engines.
- Identifiers: letters/underscore lead ok, digits-only lead (`1abc`) rejected, `_x`/`x_1` valid-but-empty. Backtick delimited identifiers incl. reserved keywords (`div`, `and`, `class`), escaped backtick, `\u`-in-backtick, newline-in-name all resolve.
- Case sensitivity: `Iif`/`Empty()`/`Abs()`/`SELECT()`/`DIV`/`Div`/`Is`/`And` all rejected; lowercase forms work; `TRUE`/`True` are identifiers (→ empty) not booleans; `fhirpath_is_valid` agrees on every case.
- Heterogeneous aggregate error (`(1|'a'|2).aggregate($this+$total,0)`): Python raises, native returns empty — identical at the UDF boundary (both []), parity holds.
- Conformance baseline: 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47) — no regression.

## Issues
- QA-001 LOW DEFERRED: malformed escapes (`\uZZ`, short `\u41`, `\q`) silently drop the backslash in BOTH engines instead of strict grammar rejection. Documented FP-10 tolerant-grammar corner; no official fixture pins strictness; parity holds.
- QA-002 LOW INTENDED: one-arg aggregate empty-$total semantics pinned via fixture (NOT a bug).

Conclusion: zero CRITICAL/HIGH/MEDIUM non-terminal issues → clean exit eligible at min_iterations=1.
