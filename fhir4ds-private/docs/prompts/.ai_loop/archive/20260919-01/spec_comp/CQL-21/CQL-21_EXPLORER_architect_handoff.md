# Architect Handoff — CQL-21 EXPLORER launch (iteration 1)

## Golden Standard
`.temp/architect/golden_standard.md` (8 invariants; comparison-operator
symmetry, §22.21 propagation, dual-engine lockstep, complete keyword
registration, no silent fallbacks, class-level fixes, binary md5 rule).

## Audit result (this launch's diffs)
All three fixes satisfy the invariants:
- QA-001 fix restores `=`/`~` symmetry for single-Code operands at the
  documented Python-supplement UDF boundary (coding_matches_exact sits beside
  the equally Python-only coding_matches — invariant 3 boundary respected).
- QA-002 fix is class-level (any §22.21-capable literal list element) with an
  honest null for non-representable Avg/Median rather than a wrong crisp value.
- QA-003 fix closes a partial keyword registration across both registries.
- Native binary md5 c5b22d58310c1eb7bafa17ce7877f989 consistent across
  build/bundle/site-packages; master gate re-run on the final tree:
  2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47/47).

## New finding
- QA-005 LOW DEFERRED: dynamic Concept-vs-literal `=` still lacks a dynamic
  path (QA-001 fixed the Code variant only). Appendix B does not pin
  Equal(Concept) set semantics and the pattern is rare in eCQMs; deferred to a
  terminology-operator chunk owner.

## QA Enforcer Gate
EXPLORER QA was sufficient: probed mandated boundary matrix (all age
precisions × birthDate precisions, offsets both sides, leap-day anniversaries,
uncertainty × comparisons/interval-in/lists/aggregates, retrieved-vs-literal
Code/Concept equality, unloaded valueset/ExpandValueSet nulls) across all
three engine modes with py==cpp parity confirmed. No RETRY_QA.

## Compression
QA (EXPLORER) found 4 issues (1 HIGH dynamic-code Equal always-False, 2 MEDIUM
uncertainty-dropping Sum + unregistered Average, 1 LOW intended collapse);
Engineering fixed all three at root cause in translator + UDFs (Python and
native, rebuilt and deployed) with a 7-assertion dual-engine regression test;
validation: focused suites 189/189 and master gate 2832/2832 including DQM
47/47 on the final tree. 1 LOW residual deferred (QA-005).

## Loop decision
Iteration 1 ≥ min_iterations(1); zero non-terminal CRITICAL/HIGH/MEDIUM issues.
CLEAN exit.
