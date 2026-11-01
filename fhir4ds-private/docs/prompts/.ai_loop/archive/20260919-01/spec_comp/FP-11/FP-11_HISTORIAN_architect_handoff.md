# Architect Handoff — FP-11 §5.7 Math (HISTORIAN), iteration 1

## Audit summary

Scope was a single surgical Python fix in the direct-helper layer; no native
or engine changes. Invariant check against the Golden Standard:

- **Dual-engine lockstep**: fix mirrors the engine `power()`/`rround()`
  semantics in `fhir4ds/fhirpath/engine/invocations/math.py`; native path was
  already correct (verified by the 81-case dual-path probe, 1 documented ULP
  pin). No rebuild required.
- **No silent fallbacks / no hardcoding**: the helper fix is general (class
  of inputs), not case-specific.
- **Structural observation (logged, not fixed)**: this is the 7th instance of
  engine fixes not reaching `fhir4ds/fhirpath/duckdb/functions/*`. The
  long-term fix is delegating direct helpers to the engine implementations
  instead of hand-maintaining parallel semantics — same family as REV-002
  (hand-duplicated metadata). Recommend a consolidation pass under the
  existing REV umbrella; not in this chunk's scope.

## QA Enforcer Gate

QA was sufficient: fresh 81-case dual-path battery on orthogonal angles
(Quantity operands, iteration chaining, resource-driven math, domains,
typing edges) + the helper surface; all 4 prior fixes re-verified; 1 real
MEDIUM found and fixed. No RETRY_QA.

## Issues

| ID | Severity | Status |
| --- | --- | --- |
| QA-001 | MEDIUM | RESOLVED (helper power/round parity; tests + conformance 2832/2832) |
| QA-002 | LOW | INTENDED (transcendental ULP drift re-pin) |

Zero non-terminal CRITICAL/HIGH/MEDIUM remain; min_iterations=1 reached →
CLEAN exit, workflow=null.
