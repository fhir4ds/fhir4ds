# QA Handoff — FP-06 HISTORIAN (FHIRPath §5.5.1-§5.5.3)

## Verdict: CLEAN — zero defects (33 fresh dual-path cases; all flagged rows adjudicated probe-expectation artifacts)

## Probes
probe1 (33 cases): normative-table walk — iif empty-criterion→otherwise +
truthy-singleton rules; toBoolean string table verbatim (yes/N/1/0.0/TRUE/vrai);
convertsToBoolean mirror; toInteger int32-range + decimal-string + whitespace
rejection + Boolean→1/0 + passthrough; convertsToInteger mirror.

## Adjudications (all 13 flagged rows = artifacts, ZERO engine defects)
1. TWELVE rows: the wrapper renders Booleans as STRINGS ('true'/'false') inside
   the JSON result list; my python-bool expectations ([True]/[False]) compared
   unequal against the string forms though VALUES are correct (verified via
   `'yes'.toBoolean() = true` → true and elem types all str). Parity held on all.
2. ONE row (`iif('f'.toBoolean() and false, 'y', 'n')` → ['n']): my 'y'
   expectation was WRONG — 'f' converts to Boolean FALSE; false AND false = false
   → otherwise branch. Engine correct on both paths.

## Lesson (probe-harness)
Boolean results must be expected as the STRING forms "true"/"false" in wrapper
output lists (never python True/False).
