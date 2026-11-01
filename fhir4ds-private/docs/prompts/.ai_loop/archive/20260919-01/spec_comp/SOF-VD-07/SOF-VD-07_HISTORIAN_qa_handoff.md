# QA Handoff — SOF-VD-07 (select.repeat), HISTORIAN, iteration 1

## Spec ground truth
SD (HL7/sql-on-fhir main, ViewDefinition.select.repeat): 0..* string, "A list of
FHIRPath expressions that define paths to recursively traverse. The view runner
will recursively follow each path to any depth, collecting results from all
levels. All results are combined using a union operation." At most one of
forEach/forEachOrNull/repeat per select. Official repeat.json fixtures (19) use
only simple dotted paths — expression-typed repeat paths are spec-permitted but
fixture-untested, so this launch targeted them.

## New probes this launch (all through parse → SQLGenerator(strict) → DuckDB;
official-runner SQL adaptation; native engine via allow_unsigned_extensions LOAD)
- H1 Full FHIRPath expressions in repeat paths: `item.where(linkId != 'g2')`,
  `item | answer.item` — correct recursive traversal + union, native==fallback.
- H2 Invalid FHIRPath in repeat path (`item(`) — rejected at generate time with
  typed ValidationError, identical to column-path treatment (no silent-empty
  divergence; the UDF-level catch is defense-in-depth only).
- H3 `%resource.item` and `%context.item` in repeat paths — both engines
  evaluate built-in variables against the current node context (matches
  reference-impl per-node evaluate; %resource==node is fhirpath.js-consistent).
- H7 Single quotes inside repeat path string literals — SQL literal escaping
  correct both engines.
- H4 `%rowIndex` under multi-path repeat — 0-based index over the flattened
  union array.
- H5 `where` with $this-functions (startsWith) on repeated context — correct,
  native==fallback.
- H8 `children()` repeat incl. mixed dict/primitive yields — dict-only
  collection (pinned SOF-VD-05), parity holds.
- H9 repeat with no match drops rows (inner-join) — correct.
- H10 nested select + nested forEach under repeat — correct cross-join rows.
- C1 Cycle-equivalent fixpoints: `$this`, `$this | item`,
  `children() | $this.children()` — all terminate via dedup; parity holds.
- C2 repeat under empty forEachOrNull — exactly one null row (Process(S,N) step
  3), parity holds.
- C3 unionAll sibling branches repeat-vs-forEach — union (with repeat's dedup)
  correct, parity holds.
- Constants: `%P` (string constant) in repeat path yields empty on BOTH engines
  (FHIRPath constants are values, not dynamic navigation) — consistent, not a bug.
- C4 Deep JSON (13k-deep item chain, string-built to avoid harness serializer
  limits): re-verification of the SKEPTIC recursion-budget fix — see
  engineer/architect handoff for final outcome; no segfault observed in any
  probe this launch.

## Findings
No NEW non-terminal CRITICAL/HIGH/MEDIUM issues. Logged observations (all LOW,
terminal): see evolution.json QA-001..QA-004 (INTENDED doctrine pins,
re-confirmed fresh).

## Gates (fresh)
- ViewDef conformance: 144/144 (repeat.json 19/19). run_viewdef.py exit 0.
- viewdef pytest: 1186/1186.
- Master gate + binary md5s: see architect_handoff.md (run in parallel).

Probes: /mnt/d/fhir4ds/.temp/qa/sof_vd07_historian/{probe.py,probe2.py,base.py}
