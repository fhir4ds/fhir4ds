# FP-19 QA Handoff — EXPLORER, iteration 1 (2026-08-18)

Chunk: FHIRPath §7 Aggregates (STU), §8 Lexical Elements. Dual-engine probes
(native fhirpath.duckdb_extension vs forced Python fallback) in
`/mnt/d/fhir4ds/.temp/qa/fp19_explorer/probe1..6.py`, PYTHONPATH=/mnt/d/fhir4ds.

## Probed clean (native == fallback on all)
- aggregate building collections (`$total | $this` with init `{}`), resource-
  field accumulation, reversed `$this | $total`, 5-deep chained aggregates.
- aggregate + defineVariable inside/outside aggregator (unsupported, empty,
  parity), %context/%resource env vars (work, parity), undefined env var errors.
- error mid-aggregation (`1+'x'` item, /0): both empty at top level.
- lexical: strings containing `/* */` and backticks; `\uXXXX` escapes; backtick
  members `class`, `div`, `Patient.div`, `` `  spaced  ` ``, `` `.` ``, `` `a.b.c` ``;
  whitespace/newline/block-comment forms inside aggregate arg lists; case
  sensitivity of $this/$index/$total ($THIS/$This/$TOTAL rejected both).
- quantity literals with composed units through aggregate (init `0 'cm'`
  aggregates to empty in both — int+quantity is incompatible, parity).

## Issues
- QA-001 HIGH: native converts incompatible-type arithmetic (`1+'x'`, `1+true`,
  `1+{}`) into empty instead of signaling an error, so parents keep evaluating:
  `(1+'x') | 99` -> ['99'] native vs [] fallback; errored-aggregate `.count()`
  -> ['0'] vs []. Spec §6.6: evaluation must end and signal an error.
- QA-002 MEDIUM: native mixed-unit quantity addition returns canonical base
  unit (`3.5 'wk' + 2 'd'` -> `2289600 's'`) instead of most-granular input
  unit (`26.5 'd'`, §6.6.3). Fallback is spec-correct.

## Handoff
Both are native evaluator.cpp fixes (fallback already correct). Rebuild +
redeploy fhirpath.duckdb_extension per AGENTS.md. Add parity regression tests.
