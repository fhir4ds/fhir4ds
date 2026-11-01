# QA Handoff — FP-06 SKEPTIC (FHIRPath §5.5.1-§5.5.3: iif / toBoolean / convertsToBoolean / toInteger / convertsToInteger)

## Verdict: CLEAN — zero defects (0 issues logged; 61 fresh dual-path cases)

## Probes
- probe1 (44 cases): iif truth tables (empty-criterion→otherwise; Boolean/numeric/
  string truthy singletons; then-branch navigation), toBoolean full string table
  ('true'/'false'/'t'/'f'/'yes'/'no'/'Y'/'N'/'1'/'0'/'1.0'/'0.0' → booleans;
  'vrai'/'2' → empty; case-insensitive accepted; Boolean passthrough),
  convertsToBoolean mirrored, toInteger (int32 range enforcement — 2147483648 /
  −2147483649 empty; '4.0'/'4.5' decimal strings REJECTED; whitespace rejected;
  true→1/false→0; Integer passthrough), convertsToInteger mirrored.
- probe2 (17 cases): iif LAZINESS (error in unselected branch suppressed BOTH
  directions), multi-item criterion → row-resilient empty, multi-item conversion
  inputs → empty, empty-input propagation, non-string/non-numeric inputs → empty,
  is_valid('1 +') False on both engines.

## Adjudications
None needed — zero flagged rows survived the probe-harness fixes (list-vs-JSON
dispatch; is_valid marker quoting).

## Probe-harness lessons (GLOBAL_KNOWLEDGE queued)
fhirpath() may return a python LIST (isinstance-dispatch in runners); is_valid
marker rows must carry the expression unquoted.
