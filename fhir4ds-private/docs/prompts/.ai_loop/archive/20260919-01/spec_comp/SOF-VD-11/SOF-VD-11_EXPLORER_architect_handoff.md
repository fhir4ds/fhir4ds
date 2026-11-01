# Architect Handoff — SOF-VD-11 EXPLORER (2026-08-23)

## Audit of this iteration's fixes
- QA-001 fix (`_json_serialize` -> `_json_serialize_iterative` fallback): architecturally
  sound. It reuses the existing iterative serializer abstraction (single serialization
  doctrine), touches only the Python-fallback serialization boundary, adds no
  engine-specific branching, and honors the dual-engine lockstep invariant (parity test
  shipped with the fix). No silent fallback introduced: the fallback path is only taken
  for the specific orjson recursion TypeError; other TypeErrors still raise.
- QA-002 fix (`run_all.py` absolute paths + single retry): scoped to the conformance
  harness, not product code; matches the REV-009 retry doctrine and the documented WSL/
  drvfs environment caveats in AGENTS.md. The retry is bounded (one) and prints a notice.
- Golden-standard spot check on the chunk invariants (built-ins from constants.py,
  forEach/forEachOrNull semantics, typed-column runtime guards, result-type coercion map):
  no violations observed; generator behavior matched the pinned doctrines at every
  probed boundary.

## QA Enforcer Gate
QA was NOT lazy: it covered every mandate area (volume, extremes, BP example end-to-end,
Arrow/DataFrame inputs, consumption fidelity, concurrency, unicode, null semantics,
native-vs-fallback comparison) and found two real MEDIUM issues with reproducer-grade
evidence. RETRY_QA: false.

## State
- Iteration 1 complete (QA -> FIX -> ARCHITECT). Issues QA-001, QA-002 both FIXED
  (terminal). Zero non-terminal CRITICAL/HIGH/MEDIUM remain; min_iterations=1 reached.
  Clean exit recommended.
