# QA Handoff — FP-05 SKEPTIC (FHIRPath §5.3 Subsetting + §5.4 Combining)

## Verdict: CLEAN — zero defects (0 issues logged)

## Probes (fresh evidence; scripts .temp/qa/speccomp2/fp05_skeptic_probe{1,2,3}.py)
- probe1 (32 dual-path cases): indexer bounds (0/2 ok, out-of-range/negative empty);
  single() cardinality (0→empty, 1→item, many→[] row-resilient BOTH); first/last/tail;
  skip/take (0=identity/clamp, take 0→empty); union dedup (1|1.0→1, family|'Chalmers'→3);
  combine keeps dups (name.combine(name)→6); intersect/exclude equality semantics;
  resource-backed set ops. 32/32 parity.
- probe2 (adjudication battery): skip(-1)→identity ['3'] vs take(-1)→['0'] (empty) —
  BOTH engines + CORE agree (fp.evaluate: skip(-1)→[3], take(-1)→[0]).
- probe3 (16 dual-path cases): non-integer indexer/count types (flags[1.5], [true],
  ['x'], skip('x'), take(true), tail(1.0)) → [] row-resilient BOTH; single() error
  classes; QUANTITY set ops via equality semantics (qty [1cm,10mm] distinct().count()
  → 1; (qty|qty).count() → 1); chained subsetting (skip.take.first, tail.single,
  [0].single). 16/16 parity.

## Adjudication note (surface distinction, recorded for GLOBAL_KNOWLEDGE)
skip(-1)→identity while take(-1)→empty: the FHIRPath engine impl is EXPLICIT
(filtering.py take_fn n<=0→[] ; skip_fn n<=0→identity), unit-pinned (test_filter.py
:279/:313), and spec-silent (negative n unspecified). NOT A BUG. The prior
GLOBAL_KNOWLEDGE line 'Skip/Take negative counts return [] (DuckDB slice semantics)'
applies to the CQL list-macro surface ONLY — do not read it onto the FHIRPath §5.3
surface. Clarification queued for the 5-chunk milestone compaction.
