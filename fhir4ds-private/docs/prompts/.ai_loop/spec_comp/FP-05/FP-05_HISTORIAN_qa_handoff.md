# QA Handoff — FP-05 HISTORIAN (FHIRPath §5.3 Subsetting + §5.4 Combining)

## Verdict: CLEAN — zero defects (42 fresh cases; 7 flagged rows ALL adjudicated probe-expectation artifacts)

## Probes
- probe1 (23-case normative-table walk): every §5.3/§5.4 function per spec table —
  indexer bounds, single() cardinality, first/last empty-safety, tail≡skip(1),
  skip/take clamps, union dedup, combine append, intersect/exclude membership.
- probe2 (19 narrative-rule cases, corrected fixture expectations).

## Adjudications (all parity-consistent; every flagged row was MY expectation error)
1. **6 probe1 flags = fixture-math error**: `name.given` is [John, Kim, Kim] — 3 items
   across TWO name elements (multi-valued flattening), not 2. All corrected rows verified
   green in probe2 (indexer [2]→Kim, tail→[Kim,Kim], skip/take counts 3, combine count 6).
2. **intersect('Kim') → ['Kim'] not ['Kim','Kim']** — CORRECT per §5.4.3: intersect
   returns the SET of items in both collections; the combining-rules preamble
   ("the result will not contain duplicate items") applies. My multiset expectation was wrong.

## Spec-rule confirmations (fresh)
skip(0)→whole list, skip≥len→empty; take(0)→empty, take≥len→whole; tail = all-but-first;
union dedups via `=` (1|1.0→1); combine preserves duplicates AND order; exclude removes
members; empty-operand propagation (missing|x→x; missing.intersect/exclude→empty;
missing.combine('x')→['x']); single() on 2+ items → error → row-resilient empty.

## Evidence
Scripts: .temp/qa/speccomp2/fp05_historian_probe{1,2}.py; logs /tmp/opencode/fp05h{1,2}.log.
