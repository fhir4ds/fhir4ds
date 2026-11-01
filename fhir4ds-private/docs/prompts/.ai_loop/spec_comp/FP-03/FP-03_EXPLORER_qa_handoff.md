# QA Handoff — FP-03 EXPLORER (§5.1 Existence)

## Verdict: CLEAN — zero defects (32 fresh fuzz cases, 0 parity diffs)

Deep chain compositions (distinct().count().empty().not(), where+exists+and/or),
nested criteria existence (name.exists($this.given.exists(...)), where(given.exists)),
subset/superset with transformations, existence-of-existence, isDistinct chains,
empty-input deep chains (missing.select/all/distinct), toChars count, take/skip
compositions, unicode-adjacent paths, 12 seeded random atom-op compositions
(seed 20261002). **32/32 parity; runtime-error rows failed symmetrically where
applicable.**

## Evidence
.temp/qa/speccomp2/fp03_explorer_probe1.py
