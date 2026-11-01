# QA Handoff — FP-05 EXPLORER (FHIRPath §5.3 Subsetting + §5.4 Combining)

## Verdict: CLEAN — zero defects (35 fresh fuzz cases, 0 parity diffs)

## Probes (seed 20261002)
- Chained subsetting (skip/take/first/last/tail compositions, nested first().family).
- Pathological counts/indexers: INT32_MAX/MAX+1 skips/takes/indexes — clamped or
  empty consistently on both engines.
- Mixed-type collections through set ops (1|'a'|true; family|1|@2015; quantity and
  temporal elements through union/intersect/exclude — quantity dedup 1cm|10mm→1;
  precision-stable temporal dedup).
- single() error edges; 8 seeded random atom×op chains.

All 35 rows byte-identical native vs fallback.

## Evidence
Script: .temp/qa/speccomp2/fp05_explorer_probe1.py; log /tmp/opencode/fp05e1.log.
